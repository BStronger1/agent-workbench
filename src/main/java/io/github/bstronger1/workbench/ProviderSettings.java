package io.github.bstronger1.workbench;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import javax.crypto.Cipher;
import javax.crypto.spec.GCMParameterSpec;
import javax.crypto.spec.SecretKeySpec;
import java.net.URI;
import java.nio.file.*;
import java.nio.file.attribute.PosixFilePermissions;
import java.security.SecureRandom;
import java.util.*;

/** Browser-owner scoped provider configuration. Plaintext credentials are never API responses. */
@Service
public class ProviderSettings {
    public record Input(boolean enabled, String baseUrl, String model, String apiKey, Double inputPrice, Double outputPrice) {
        @Override public String toString() { return "ProviderSettings.Input[redacted]"; }
    }
    public record Credentials(String baseUrl, String model, String apiKey, double inputPrice, double outputPrice) {
        @Override public String toString() { return "Credentials[redacted]"; }
    }
    public record View(boolean enabled, String baseUrl, String model, boolean hasKey, String keyMask,
                       double inputPrice, double outputPrice, List<String> allowedHosts) {}
    public static class Saved {
        public boolean enabled;
        public String baseUrl = "https://api.deepseek.com/v1", model = "deepseek-chat", apiKey = "";
        public double inputPrice, outputPrice;
    }
    private final Path root;
    private final ObjectMapper mapper;
    private final byte[] masterKey;
    private final List<String> hosts;
    private final SecureRandom random = new SecureRandom();

    public ProviderSettings(ProjectStore store, ObjectMapper mapper,
                            @Value("${workbench.provider-hosts}") String allowedHosts) throws Exception {
        this.mapper = mapper;
        hosts = Arrays.stream(allowedHosts.split(",")).map(String::trim).filter(s -> !s.isEmpty()).map(s -> s.toLowerCase(Locale.ROOT)).distinct().toList();
        root = store.root().resolve("providers"); Files.createDirectories(root); restrict(root, "rwx------");
        Path keyFile = root.resolve(".master-key");
        if (!Files.exists(keyFile)) {
            byte[] key = new byte[32]; random.nextBytes(key);
            Files.createFile(keyFile); restrict(keyFile, "rw-------"); Files.write(keyFile, key);
        }
        masterKey = Files.readAllBytes(keyFile);
        if (masterKey.length != 32) throw new IllegalStateException("模型配置加密文件损坏，请恢复备份");
    }
    public synchronized View view(String owner) { return toView(read(owner)); }
    public synchronized Credentials active(String owner) {
        Saved saved = read(owner);
        if (!saved.enabled || saved.apiKey.isBlank()) return null;
        // Recheck when the deployment allowlist changes, before any provider request.
        return new Credentials(normalizeBaseUrl(saved.baseUrl), saved.model, saved.apiKey, saved.inputPrice, saved.outputPrice);
    }
    public synchronized View save(String owner, Input input) {
        if (input == null) throw new IllegalArgumentException("请填写模型配置");
        Saved saved = read(owner);
        saved.baseUrl = normalizeBaseUrl(Api.requireText(input.baseUrl(), 300));
        saved.model = Api.requireText(input.model(), 150);
        if (saved.model.chars().anyMatch(Character::isISOControl)) throw new IllegalArgumentException("模型名称格式无效");
        if (input.apiKey() != null && !input.apiKey().isBlank()) {
            String key = input.apiKey().trim();
            if (key.length() < 8 || key.length() > 4096 || key.chars().anyMatch(c -> Character.isISOControl(c) || Character.isWhitespace(c)))
                throw new IllegalArgumentException("API Key 格式无效");
            saved.apiKey = key;
        }
        saved.enabled = input.enabled();
        if (saved.enabled && saved.apiKey.isBlank()) throw new IllegalArgumentException("启用真实模型前请填写 API Key");
        saved.inputPrice = price(input.inputPrice()); saved.outputPrice = price(input.outputPrice());
        write(owner, saved); return toView(saved);
    }
    public synchronized void clear(String owner) {
        try { Files.deleteIfExists(file(owner)); }
        catch (Exception e) { throw new IllegalStateException("删除模型配置失败"); }
    }
    String normalizeBaseUrl(String value) {
        try {
            URI uri = URI.create(value.trim());
            if (!"https".equalsIgnoreCase(uri.getScheme()) || uri.getHost() == null || uri.getUserInfo() != null
                    || uri.getQuery() != null || uri.getFragment() != null || (uri.getPort() != -1 && uri.getPort() != 443)) throw new IllegalArgumentException();
            String host = uri.getHost().toLowerCase(Locale.ROOT);
            if (!hosts.contains(host)) throw new IllegalArgumentException("暂不支持该接口域名，请使用页面列出的服务商，或由部署者添加到允许列表");
            String path = Objects.toString(uri.getPath(), "").replaceAll("/+$", "").replaceFirst("/chat/completions$", "");
            if (!path.matches("[a-zA-Z0-9/_-]*")) throw new IllegalArgumentException();
            return "https://" + host + path;
        } catch (IllegalArgumentException e) {
            if (e.getMessage() != null && e.getMessage().startsWith("暂不支持")) throw e;
            throw new IllegalArgumentException("接口地址需要使用 HTTPS，不能包含用户名、密码、查询参数或非标准端口");
        }
    }
    private double price(Double value) {
        if (value == null) return 0;
        if (!Double.isFinite(value) || value < 0 || value > 100000) throw new IllegalArgumentException("价格应为有效的非负数");
        return value;
    }
    private View toView(Saved s) {
        String mask = s.apiKey.isBlank() ? "" : "••••••••" + s.apiKey.substring(Math.max(0, s.apiKey.length() - 4));
        return new View(s.enabled, s.baseUrl, s.model, !s.apiKey.isBlank(), mask, s.inputPrice, s.outputPrice, hosts);
    }
    private Path file(String owner) {
        if (owner == null || !owner.matches("[a-f0-9]{64}")) throw new IllegalArgumentException("无效的项目空间");
        return root.resolve(owner + ".enc");
    }
    private Saved read(String owner) {
        Path file = file(owner);
        if (!Files.exists(file)) return new Saved();
        try {
            byte[] data = Files.readAllBytes(file);
            if (data.length < 29) throw new IllegalStateException();
            Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
            cipher.init(Cipher.DECRYPT_MODE, new SecretKeySpec(masterKey, "AES"), new GCMParameterSpec(128, Arrays.copyOfRange(data, 0, 12)));
            cipher.updateAAD(owner.getBytes(java.nio.charset.StandardCharsets.UTF_8));
            return mapper.readValue(cipher.doFinal(Arrays.copyOfRange(data, 12, data.length)), Saved.class);
        } catch (Exception e) { throw new IllegalStateException("无法读取模型配置，请检查数据备份或重新配置"); }
    }
    private void write(String owner, Saved saved) {
        Path dest = file(owner), temp = root.resolve(owner + ".tmp");
        try {
            if (!Files.exists(dest)) try (var entries = Files.list(root)) {
                if (entries.filter(p -> p.toString().endsWith(".enc")).count() >= 500) throw new IllegalStateException("模型配置数量达到上限");
            }
            byte[] nonce = new byte[12]; random.nextBytes(nonce);
            Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
            cipher.init(Cipher.ENCRYPT_MODE, new SecretKeySpec(masterKey, "AES"), new GCMParameterSpec(128, nonce));
            cipher.updateAAD(owner.getBytes(java.nio.charset.StandardCharsets.UTF_8));
            byte[] encrypted = cipher.doFinal(mapper.writeValueAsBytes(saved));
            byte[] bytes = new byte[nonce.length + encrypted.length];
            System.arraycopy(nonce, 0, bytes, 0, nonce.length); System.arraycopy(encrypted, 0, bytes, nonce.length, encrypted.length);
            Files.write(temp, bytes); restrict(temp, "rw-------");
            try { Files.move(temp, dest, StandardCopyOption.REPLACE_EXISTING, StandardCopyOption.ATOMIC_MOVE); }
            catch (AtomicMoveNotSupportedException e) { Files.move(temp, dest, StandardCopyOption.REPLACE_EXISTING); }
        } catch (Exception e) { throw new IllegalStateException("保存模型配置失败"); }
    }
    private static void restrict(Path path, String permissions) throws java.io.IOException {
        if (Files.getFileStore(path).supportsFileAttributeView("posix")) Files.setPosixFilePermissions(path, PosixFilePermissions.fromString(permissions));
    }
}
