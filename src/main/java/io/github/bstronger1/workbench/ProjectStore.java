package io.github.bstronger1.workbench;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;
import java.io.IOException;
import java.nio.file.*;
import java.util.*;
import java.util.function.Function;
import static io.github.bstronger1.workbench.Domain.*;

/** One JVM, atomic per-project snapshots. The public API never exposes owner digests. */
@Component
public class ProjectStore {
    private final Path root;
    private final ObjectMapper mapper;
    private final Map<String, Project> projects = new LinkedHashMap<>();
    public ProjectStore(@Value("${workbench.data}") String data, ObjectMapper mapper) throws IOException {
        this.mapper = mapper; root = Path.of(data).toAbsolutePath().normalize(); Files.createDirectories(root);
        try (var files = Files.list(root)) {
            for (Path f : files.filter(p -> p.getFileName().toString().endsWith(".json")).toList()) {
                Project p = mapper.readValue(f.toFile(), Project.class);
                for (Run r : p.runs) if (Set.of("RUNNING", "QUEUED").contains(r.status)) {
                    r.status = "INTERRUPTED"; r.error = "服务重启中断了任务，可重新运行。"; r.completedAt = now();
                }
                projects.put(p.id, p); persist(p);
            }
        }
    }
    public Path root() { return root; }
    public synchronized List<Project> list(String owner) {
        return projects.values().stream().filter(p -> p.owner.equals(owner)).map(this::copy).toList();
    }
    public synchronized Project create(String owner, String name) {
        if (projects.size() >= 500 || list(owner).size() >= 20) throw new IllegalArgumentException("项目数量达到上限");
        Project p = new Project(); p.owner = owner; p.name = name; projects.put(p.id, p); persist(p); return copy(p);
    }
    public synchronized Project get(String owner, String id) { return copy(owned(owner, id)); }
    public synchronized <T> T update(String owner, String id, Function<Project, T> action) {
        Project p = copy(owned(owner, id)); T result = action.apply(p); persist(p); projects.put(id, copy(p)); return result;
    }
    private Project owned(String owner, String id) {
        Project p = projects.get(id);
        if (p == null || !p.owner.equals(owner)) throw new NoSuchElementException("项目不存在");
        return p;
    }
    private Project copy(Project p) { return mapper.convertValue(p, Project.class); }
    private void persist(Project p) {
        try {
            Path target = root.resolve(p.id + ".json"), temp = root.resolve(p.id + ".tmp");
            mapper.writeValue(temp.toFile(), p);
            try { Files.move(temp, target, StandardCopyOption.REPLACE_EXISTING, StandardCopyOption.ATOMIC_MOVE); }
            catch (AtomicMoveNotSupportedException e) { Files.move(temp, target, StandardCopyOption.REPLACE_EXISTING); }
        } catch (IOException e) { throw new IllegalStateException("保存项目失败", e); }
    }
}
