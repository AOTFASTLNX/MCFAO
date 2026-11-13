package mcfao.aot;

import java.nio.file.Path;

/**
 * Stands in for the file a Mod asks the Loader for.
 *
 * <p>Several Mods locate their own JAR through {@code ModContainer.getOrigin()} and then derive
 * paths from it (Xaero's map keeps the file for its update check, its minimap does the same for
 * the HUD mod). A closed image has no Mod JARs: the classes and resources live inside the image,
 * and the only file the app ships is the Mach-O binary. The honest answer is still a path - the
 * Mod is asking "where would I be", not "read this" - so this returns the location the Mod's JAR
 * would occupy under the launch directory. Reading it fails with the usual
 * {@code NoSuchFileException}, which is the truth, instead of a bare {@code null} that the caller
 * dereferences a few frames later.
 */
public final class ModFiles {
    public static final String MODS_DIRECTORY = "mods";
    public static final String ARCHIVE_SUFFIX = ".jar";

    private ModFiles() {}

    /**
     * The nominal location of {@code id}'s JAR below {@code gameDir}.
     *
     * <p>{@code gameDir} is null when a Mod asks before the client hook reported the launch
     * directory; the working directory is that same directory in every supported launcher, so it
     * stands in rather than failing with a null path.
     */
    public static Path modFile(Path gameDir, String id) {
        if (id == null || id.isEmpty()) {
            throw new IllegalArgumentException("Mod file lookup without a Mod id");
        }
        Path base = gameDir != null ? gameDir : Path.of("").toAbsolutePath();
        return base.resolve(MODS_DIRECTORY).resolve(id + ARCHIVE_SUFFIX);
    }
}
