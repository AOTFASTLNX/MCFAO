package fabricaot.graphics;
import org.lwjgl.openal.*;
import org.lwjgl.system.MemoryUtil;
import java.nio.*;
import static org.lwjgl.openal.AL10.*;
import static org.lwjgl.openal.ALC10.*;

/** Real device/context/buffer/source lifetime and playback progression; intentionally muted. */
public final class OpenALProbe {
    static void check(boolean condition,String message){if(!condition)throw new AssertionError(message);}
    public static void main(String[] args)throws Exception{
        long device=alcOpenDevice((ByteBuffer)null);check(device!=0,"OpenAL device unavailable");
        long context=0;int buffer=0,source=0;ShortBuffer samples=null;
        try{
            ALCCapabilities alc=ALC.createCapabilities(device);check(alc.OpenALC10,"ALC 1.0 missing");
            context=alcCreateContext(device,(IntBuffer)null);check(context!=0,"OpenAL context unavailable");
            check(alcMakeContextCurrent(context),"Cannot make audio context current");
            org.lwjgl.system.SharedLibrary api=org.lwjgl.system.Library.loadNative("fabricaot.audio","openal");
            try{
                long current=alcGetCurrentContext();
                int initialError=org.lwjgl.system.JNI.invokeI(api.getFunctionAddress("alGetError"));
                long version=org.lwjgl.system.JNI.invokeP(AL_VERSION,api.getFunctionAddress("alGetString"));
                System.out.println("OPENAL_CONTEXT currentMatches="+(current==context)+" initialError="+initialError+" version="+MemoryUtil.memASCIISafe(version));
                check(current==context,"Audio context mismatch");
            }finally{api.free();}
            ALCapabilities al=AL.createCapabilities(alc);check(al.OpenAL10,"AL 1.0 missing");
            System.out.println("OPENAL_DEVICE renderer="+alGetString(AL_RENDERER)+" version="+alGetString(AL_VERSION));
            samples=MemoryUtil.memAllocShort(2205);
            for(int i=0;i<samples.capacity();i++)samples.put(i,(short)(Math.sin(i*2*Math.PI*440/22050)*2000));
            buffer=alGenBuffers();alBufferData(buffer,AL_FORMAT_MONO16,samples,22050);
            check(alGetError()==AL_NO_ERROR,"PCM buffer upload failed");
            check(alGetBufferi(buffer,AL_SIZE)==4410,"PCM buffer size mismatch");
            source=alGenSources();alSourcef(source,AL_GAIN,0);alSourcei(source,AL_BUFFER,buffer);alSourcePlay(source);
            check(alGetError()==AL_NO_ERROR,"Source playback failed");
            long deadline=System.nanoTime()+5_000_000_000L;
            int state;do{Thread.sleep(20);state=alGetSourcei(source,AL_SOURCE_STATE);}while(state==AL_PLAYING&&System.nanoTime()<deadline);
            check(state==AL_STOPPED,"Playback did not consume the PCM buffer: "+state);
            check(alcGetError(device)==ALC_NO_ERROR&&alGetError()==AL_NO_ERROR,"Audio error after playback");
            System.out.println("OPENAL_PCM_PLAYBACK_PASS bytes=4410 muted=true");
        }finally{
            if(source!=0)alDeleteSources(source);if(buffer!=0)alDeleteBuffers(buffer);
            if(samples!=null)MemoryUtil.memFree(samples);alcMakeContextCurrent(0);
            if(context!=0)alcDestroyContext(context);check(alcCloseDevice(device),"Device close failed");
        }
        System.out.println("OPENAL_PROBE_PASS");
    }
}
