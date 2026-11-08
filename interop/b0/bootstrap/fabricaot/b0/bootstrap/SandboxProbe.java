package fabricaot.b0.bootstrap;

import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.FileSystemException;
import java.net.Socket;
import java.net.InetSocketAddress;
import java.net.SocketException;

public final class SandboxProbe {
    private static boolean denied(Exception error) {
        String message = String.valueOf(error.getMessage()).toLowerCase(java.util.Locale.ROOT);
        return message.contains("not permitted") || message.contains("permission denied") || error instanceof java.nio.file.AccessDeniedException;
    }
    public static void main(String[] args) throws Exception {
        try { Files.readAllBytes(Path.of(args[0])); throw new AssertionError("outside read allowed"); }
        catch (FileSystemException error) { if (!denied(error)) throw error; }
        try { Files.writeString(Path.of(args[1]), "unexpected-write"); throw new AssertionError("outside write allowed"); }
        catch (FileSystemException error) { if (!denied(error)) throw error; }
        try (Socket socket = new Socket()) {
            socket.connect(new InetSocketAddress("127.0.0.1", Integer.parseInt(args[2])), 1000);
            throw new AssertionError("network connection allowed");
        } catch (SocketException error) { if (!denied(error)) throw error; }
        System.out.println("B0_SANDBOX_PASS");
    }
}
