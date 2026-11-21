package mcfao.build;

import java.awt.image.BufferedImage;
import java.awt.color.ColorSpace;
import java.awt.image.ComponentColorModel;
import java.awt.image.DataBuffer;
import java.awt.image.Raster;
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.util.ArrayList;
import java.util.Arrays;
import javax.imageio.ImageIO;
import mcfao.aot.TextureImage;
import net.minecraft.server.packs.resources.Resource;
import org.objectweb.asm.ClassReader;
import org.objectweb.asm.ClassWriter;
import org.objectweb.asm.tree.ClassNode;

public final class TextureImageProbe {
    // First-party stand-in for a texture sampler, using a different class and method name.
    public static class Sampler {
        public static int sample(Resource resource, int x, int y) throws IOException {
            try (var input = resource.open()) {
                var image = ImageIO.read(input);
                if (image == null) return -1;
                if (image.getWidth() != 3 || image.getHeight() != 2) throw new AssertionError();
                var raster = image.getData();
                if (image.getColorModel().getNumComponents() < 3) {
                    var samples = raster.getPixel(x, y, (int[]) null);
                    int alpha = samples.length == 2 ? samples[1] : 255;
                    return (alpha << 24) | (samples[0] * 0x010101);
                }
                return image.getRGB(x, y);
            }
        }

        public static int escapes(Resource resource) throws IOException {
            try (var input = resource.open()) {
                var image = ImageIO.read(input);
                int identity = useAsObject(image);
                if (image.getColorModel().getNumComponents() < 3) {
                    return identity + image.getData().getPixel(0, 0, (int[]) null)[0];
                }
                return identity + image.getRGB(0, 0);
            }
        }

        public static int wrongBranch(Resource resource) throws IOException {
            try (var input = resource.open()) {
                var image = ImageIO.read(input);
                if (image.getColorModel().getNumComponents() < 3) return image.getRGB(0, 0);
                return image.getData().getPixel(0, 0, (int[]) null)[0];
            }
        }

        public static int externalInput(InputStream input) throws IOException {
            return ImageIO.read(input).getRGB(0, 0);
        }

        private static int useAsObject(Object image) { return image.hashCode(); }
    }

    private static byte[] png(BufferedImage image) throws IOException {
        var output = new ByteArrayOutputStream();
        check(ImageIO.write(image, "png", output), "desktop PNG writer unavailable");
        return output.toByteArray();
    }

    private static Resource resource(byte[] data) {
        return new Resource(null, () -> new ByteArrayInputStream(data));
    }

    private static void check(boolean valid, String message) {
        if (!valid) throw new AssertionError(message);
    }

    public static void main(String[] args) throws Exception {
        var node = new ClassNode();
        try (var stream = TextureImageProbe.class.getResourceAsStream("TextureImageProbe$Sampler.class")) {
            new ClassReader(stream).accept(node, 0);
        }
        var adaptations = new ArrayList<String>();
        TextureImageLowering.lower(node, adaptations);
        check(adaptations.size() == 1 && adaptations.getFirst().contains("#sample "), adaptations.toString());
        TextureImageLowering.lower(node, adaptations);
        check(adaptations.size() == 1, "second pass changed the sampler again");
        var writer = new ClassWriter(0);
        node.accept(writer);
        byte[] transformed = writer.toByteArray();
        var type = new ClassLoader() {
            Class<?> loadSampler() { return defineClass(null, transformed, 0, transformed.length); }
        }.loadSampler();
        var sample = type.getDeclaredMethod("sample", Resource.class, int.class, int.class);

        var rgba = new BufferedImage(3, 2, BufferedImage.TYPE_INT_ARGB);
        rgba.setRGB(0, 0, 0x804488cc);
        rgba.setRGB(1, 0, 0x00112233);
        rgba.setRGB(2, 1, 0xfff0a020);
        var gray = new BufferedImage(3, 2, BufferedImage.TYPE_BYTE_GRAY);
        gray.getRaster().setSample(2, 1, 0, 91);
        var grayAlpha = new BufferedImage(new ComponentColorModel(ColorSpace.getInstance(ColorSpace.CS_GRAY),
                true, false, java.awt.Transparency.TRANSLUCENT, DataBuffer.TYPE_BYTE),
                Raster.createInterleavedRaster(DataBuffer.TYPE_BYTE, 3, 2, 2, null), false, null);
        grayAlpha.getRaster().setPixel(2, 1, new int[] {118, 77});
        var indexed = new BufferedImage(3, 2, BufferedImage.TYPE_BYTE_INDEXED);
        indexed.setRGB(2, 1, 0xff00ff00);
        for (var original : new BufferedImage[] {rgba, gray, grayAlpha, indexed}) {
            byte[] data = png(original);
            for (int y = 0; y < 2; y++) {
                for (int x = 0; x < 3; x++) {
                    check(sample.invoke(null, resource(data), x, y).equals(Sampler.sample(resource(data), x, y)),
                            "pixel differs from desktop at " + x + "," + y + " for type " + original.getType());
                }
            }
        }
        check(sample.invoke(null, resource(new byte[] {1, 2}), 0, 0).equals(-1), "non-PNG fallback");
        byte[] truncated = Arrays.copyOf(png(gray), 29);
        byte[] oversized = truncated.clone();
        java.nio.ByteBuffer.wrap(oversized).putInt(16, Integer.MAX_VALUE);
        try (var huge = new ByteArrayInputStream(oversized)) {
            TextureImage.read(huge);
            throw new AssertionError("Oversized PNG accepted");
        } catch (IOException expected) {
            check(expected.getMessage().contains("pixel limit"), "Unexpected PNG size error: " + expected);
        }
        boolean[] closed = {false};
        var invalid = new ByteArrayInputStream(truncated) {
            @Override public void close() { closed[0] = true; }
        };
        try {
            TextureImage.readWrapped(invalid, "test:truncated");
            throw new AssertionError("corrupt PNG decoded");
        } catch (IOException error) {
            check(closed[0] && error.getMessage().contains("test:truncated"), "decode failure did not close or identify input");
        }
        System.out.println("MCFAO_TEXTURE_IMAGE_PASS");
    }
}
