#include <metal_stdlib>
using namespace metal;
struct PresentationVertex { float4 position [[position]]; float2 uv; };
vertex PresentationVertex faot_present_vertex(uint index [[vertex_id]]) {
    constexpr float2 positions[3]={float2(-1,-1),float2(3,-1),float2(-1,3)};
    float2 p=positions[index];
    return {float4(p,0,1),float2((p.x+1)*0.5,(1-p.y)*0.5)};
}
fragment float4 faot_present_fragment(PresentationVertex in [[stage_in]],texture2d<float> source [[texture(0)]]) {
    constexpr sampler nearest(coord::normalized,address::clamp_to_edge,filter::nearest);
    return source.sample(nearest,in.uv);
}
vertex float4 faot_clear_vertex(uint index [[vertex_id]], constant float &depth [[buffer(0)]]) {
    constexpr float2 positions[3]={float2(-1,-1),float2(3,-1),float2(-1,3)};
    return float4(positions[index],depth,1);
}
fragment float4 faot_clear_fragment(constant float4 &color [[buffer(0)]]) {
    return color;
}
