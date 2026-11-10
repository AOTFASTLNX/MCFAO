// Build-time adapter: authoritative Metal binding indices from pinned SPIRV-Cross.
#include "spirv_msl.hpp"
#include <fstream>
#include <iomanip>
#include <iostream>
#include <sstream>
#include <stdexcept>
#include <vector>
#include <map>
using namespace spirv_cross;
static std::string quote(const std::string &text) {
    std::ostringstream out;out<<'"';
    for(unsigned char c:text){
        if(c=='"'||c=='\\')out<<'\\'<<c;
        else if(c<32)out<<"\\u00"<<std::hex<<std::setw(2)<<std::setfill('0')<<int(c)<<std::dec;
        else out<<c;
    }
    out<<'"';return out.str();
}
int main(int argc,char **argv) {
    try {
        if(argc<5||argc>7)throw std::runtime_error("input.spv vertex|fragment output.metal bindings.json [interface-locations.txt [--texture-y-down]]");
        std::string stage=argv[2];if(stage!="vertex"&&stage!="fragment")throw std::runtime_error("Unknown shader stage");
        const bool textureYDown=argc==7;
        if(textureYDown&&(stage!="vertex"||std::string(argv[6])!="--texture-y-down"))throw std::runtime_error("Invalid texture origin option");
        std::ifstream input(argv[1],std::ios::binary|std::ios::ate);
        auto bytes=input.tellg();if(bytes<=0||bytes>16*1024*1024||bytes%4)throw std::runtime_error("Invalid SPIR-V size");
        input.seekg(0);std::vector<uint32_t> words(size_t(bytes)/4);input.read(reinterpret_cast<char *>(words.data()),bytes);
        if(!input||words[0]!=0x07230203)throw std::runtime_error("Invalid SPIR-V input");
        CompilerMSL compiler(std::move(words));
        if(argc>=6){
            std::ifstream locations(argv[5]);if(!locations)throw std::runtime_error("Interface location map missing");
            std::map<std::string,uint32_t> mapping;std::string name;uint32_t location;
            while(locations>>name>>location){if(location>127||!mapping.emplace(name,location).second)throw std::runtime_error("Invalid interface location map");}
            auto enabled=compiler.get_active_interface_variables();auto declared=compiler.get_shader_resources();const auto &varyings=stage=="vertex"?declared.stage_outputs:declared.stage_inputs;
            for(const auto &resource:varyings){
                auto item=mapping.find(resource.name);if(item==mapping.end()){if(enabled.count(resource.id))throw std::runtime_error("Unmapped shader varying: "+resource.name);continue;}
                compiler.set_decoration(resource.id,spv::DecorationLocation,item->second);
            }
        }
        auto options=compiler.get_msl_options();options.platform=CompilerMSL::Options::iOS;options.msl_version=CompilerMSL::Options::make_msl_version(2,4);options.texture_buffer_native=true;
        // These texture-writing passes place row zero at the OpenGL framebuffer bottom.
        // Metal stores row zero at the top, matching the UVs used to sample it later.
        compiler.set_msl_options(options);
        auto common=compiler.get_common_options();common.vertex.flip_vert_y=textureYDown;compiler.set_common_options(common);
        auto model=stage=="vertex"?spv::ExecutionModelVertex:spv::ExecutionModelFragment;
        std::string entry=stage=="vertex"?(textureYDown?"faot_texture_vertex":"faot_vertex"):"faot_fragment";
        compiler.rename_entry_point("main",entry,model);compiler.set_entry_point(entry,model);
        auto active=compiler.get_active_interface_variables();compiler.set_enabled_interface_variables(active);
        std::string metal=compiler.compile();auto resources=compiler.get_shader_resources(active);
        std::ofstream code(argv[3]);code<<metal;code.close();if(!code)throw std::runtime_error("MSL output failed");
        std::ofstream out(argv[4]);out<<"{\"stage\":"<<quote(stage)<<",\"entry\":"<<quote(entry)<<",\"resources\":[";
        bool first=true;
        auto emit=[&](const auto &items,const std::string &kind,bool binding){
            for(const auto &resource:items){
                if(!first)out<<',';first=false;
                const auto &type=compiler.get_type(resource.type_id);
                out<<"{\"kind\":"<<quote(kind)<<",\"name\":"<<quote(resource.name)
                   <<",\"idName\":"<<quote(compiler.get_name(resource.id))<<",\"baseTypeName\":"<<quote(compiler.get_name(resource.base_type_id))
                   <<",\"id\":"<<resource.id<<",\"components\":"<<type.vecsize<<",\"columns\":"<<type.columns<<",\"baseType\":"<<uint32_t(type.basetype)<<",\"width\":"<<type.width<<",\"array\":[";
                for(size_t i=0;i<type.array.size();i++){if(i)out<<',';out<<type.array[i];}out<<']';
                if(binding){
                    auto index=compiler.get_automatic_msl_resource_binding(resource.id);out<<",\"metalIndex\":"<<index;
                    if(kind=="texture")out<<",\"metalSamplerIndex\":"<<compiler.get_automatic_msl_resource_binding_secondary(resource.id)<<",\"bufferTexture\":"<<(type.image.dim==spv::DimBuffer?"true":"false");
                }else if(compiler.has_decoration(resource.id,spv::DecorationLocation))out<<",\"location\":"<<compiler.get_decoration(resource.id,spv::DecorationLocation);
                if(kind=="uniform")out<<",\"bytes\":"<<compiler.get_declared_struct_size(compiler.get_type(resource.base_type_id));
                out<<'}';
            }
        };
        emit(resources.stage_inputs,"input",false);emit(resources.stage_outputs,"output",false);
        emit(resources.uniform_buffers,"uniform",true);emit(resources.sampled_images,"texture",true);
        emit(resources.separate_images,"image",true);emit(resources.separate_samplers,"sampler",true);emit(resources.storage_buffers,"storage",true);
        out<<"]}\n";out.close();if(!out)throw std::runtime_error("Binding output failed");
        return 0;
    }catch(const std::exception &error){std::cerr<<error.what()<<'\n';return 2;}
}
