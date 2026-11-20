package mcfao.aot;

import com.mojang.blaze3d.platform.NativeImage;
import java.io.IOException;
import java.io.InputStream;
import java.util.Arrays;

/** Read-only PNG pixels for resource-pack texture samplers, without java.desktop. */
public final class TextureImage {
    private static final byte[] PNG = {(byte) 137, 80, 78, 71, 13, 10, 26, 10};
    private static final int MAX_BYTES = 16 << 20;
    private static final int MAX_PIXELS = 4 << 20;

    private final int width, height, components;
    private final int[] pixels;

    private TextureImage(NativeImage image, int components) {
        width = image.getWidth();
        height = image.getHeight();
        this.components = components;
        pixels = new int[width * height];
        for (int y = 0; y < height; y++) {
            for (int x = 0; x < width; x++) pixels[y * width + x] = image.getPixel(x, y);
        }
    }

    public static TextureImage read(InputStream stream) throws IOException {
        // ImageIO returns null when no reader is registered. Here the only supported format
        // is the PNG used by Minecraft resource packs. Leave stream ownership to the caller.
        byte[] header = stream.readNBytes(29);
        if (header.length < PNG.length || !Arrays.equals(header, 0, PNG.length, PNG, 0, PNG.length)) {
            return null;
        }
        if (header.length != 29 || word(header, 8) != 13 || word(header, 12) != 0x49484452) {
            throw new IOException("Invalid texture PNG header");
        }
        int width = word(header, 16), height = word(header, 20);
        if (width <= 0 || height <= 0 || (long) width * height > MAX_PIXELS) {
            throw new IOException("Texture PNG exceeds the pixel limit");
        }
        int depth = header[24] & 255, color = header[25] & 255;
        if (depth > 8) throw new IOException("Texture PNG above 8 bits per channel is unsupported");
        byte[] rest = stream.readNBytes(MAX_BYTES - header.length + 1);
        if (rest.length + header.length > MAX_BYTES) throw new IOException("Texture PNG exceeds the byte limit");
        byte[] encoded = Arrays.copyOf(header, header.length + rest.length);
        System.arraycopy(rest, 0, encoded, header.length, rest.length);
        // Color types 0 and 4 expose raw gray(/alpha) samples at 8-bit precision. Indexed
        // and sub-byte gray PNGs use their decoded ARGB values, like ImageIO's indexed model.
        boolean transparent = color == 4 || color == 6 || hasTransparency(encoded);
        int components = (depth == 8 && (color == 0 || color == 4) ? 1 : 3) + (transparent ? 1 : 0);
        try (NativeImage image = NativeImage.read(encoded)) {
            if (image.getWidth() != width || image.getHeight() != height) {
                throw new IOException("Texture PNG dimensions differ from its header");
            }
            return new TextureImage(image, components);
        }
    }

    // The patched stream wrapper leaves the existing success-path close in place. If decoding
    // throws, take responsibility for the wrapper's stream before the original fallback runs.
    public static TextureImage readWrapped(InputStream stream, String texture) throws IOException {
        try {
            return read(stream);
        } catch (IOException error) {
            try (stream) {
                throw new IOException("Could not decode texture " + texture, error);
            }
        }
    }

    private static int word(byte[] data, int offset) {
        return (data[offset] & 255) << 24 | (data[offset + 1] & 255) << 16
                | (data[offset + 2] & 255) << 8 | (data[offset + 3] & 255);
    }

    private static boolean hasTransparency(byte[] data) {
        for (int offset = 8; offset <= data.length - 12;) {
            int size = word(data, offset), type = word(data, offset + 4);
            if (size < 0 || size > data.length - offset - 12 || type == 0x49444154) break; // IDAT
            if (type == 0x74524e53) return true; // tRNS
            offset += 12 + size;
        }
        return false;
    }

    public int getWidth() { return width; }
    public int getHeight() { return height; }
    public int getRGB(int x, int y) {
        if (x < 0 || x >= width || y < 0 || y >= height) throw new ArrayIndexOutOfBoundsException();
        return pixels[y * width + x];
    }
    public TextureImage getData() { return this; }
    public TextureImage getColorModel() { return this; }
    public int getNumComponents() { return components; }

    // This facade implements only the gray-sample branch of the recognized texture samplers.
    public int[] getPixel(int x, int y, int[] sample) {
        int rgba = getRGB(x, y);
        if (components >= 3) throw new IllegalStateException("RGB textures must be sampled with getRGB");
        if (sample == null) sample = new int[components];
        sample[0] = rgba & 255;
        if (components == 2) sample[1] = rgba >>> 24;
        return sample;
    }
}
