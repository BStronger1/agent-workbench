package io.github.bstronger1.workbench;

import org.springframework.stereotype.Service;
import java.util.*;
import static io.github.bstronger1.workbench.Domain.*;

@Service
public class MemoryService {
    public Memory remember(Project p, String kind, String key, String value) {
        if (!Set.of("constraint", "decision", "lesson").contains(kind)) throw new IllegalArgumentException("未知记忆类型");
        if (p.memories.size() >= 200) throw new IllegalArgumentException("记忆条目达到上限");
        Memory m = new Memory(); m.kind = kind; m.key = key; m.value = value;
        for (Memory old : p.memories) if (old.active && old.key.equalsIgnoreCase(key)) { old.active = false; old.supersededBy = m.id; }
        p.memories.add(m); return m;
    }
    public List<Source> retrieve(Project p, String query, boolean includeDocuments) {
        List<Source> sources = new ArrayList<>();
        for (Memory m : p.memories) if (m.active) {
            double score = similarity(query, m.key + " " + m.value) + (!includeDocuments && m.kind.equals("constraint") ? 2 : 0);
            if (score > 0) sources.add(new Source(m.id, m.kind + " · " + m.key, m.value, score));
        }
        if (includeDocuments) for (Document d : p.documents) {
            String[] chunks = d.content().split("(?<=。)|\\n");
            for (int i = 0; i < chunks.length; i++) {
                String text = chunks[i].trim(); double score = similarity(query, d.title() + " " + text);
                if (!text.isBlank() && score > 0) sources.add(new Source(d.id() + ":" + i, d.title() + " · 段落 " + (i + 1), text.substring(0, Math.min(1200, text.length())), score));
            }
        }
        return sources.stream().sorted(Comparator.comparingDouble(Source::score).reversed().thenComparing(Source::id)).limit(8).toList();
    }
    public List<Source> context(Project p, String prompt, String strategy) {
        if (strategy.equals("none")) return List.of();
        if (strategy.equals("window")) return p.runs.stream().skip(Math.max(0, p.runs.size() - 3L))
                .map(r -> new Source(r.id, "近期需求", r.prompt, 1)).toList();
        return retrieve(p, prompt, false);
    }
    static double similarity(String query, String text) {
        Set<String> q = tokens(query), t = tokens(text);
        if (q.isEmpty()) return 0;
        long overlap = q.stream().filter(t::contains).count(); return (double) overlap / q.size();
    }
    private static Set<String> tokens(String text) {
        Set<String> result = new HashSet<>();
        for (String token : text.toLowerCase(Locale.ROOT).split("[^\\p{L}\\p{N}]+")) {
            if (token.isBlank()) continue;
            result.add(token);
            if (token.matches(".*[\\p{IsHan}].*")) for (int i = 0; i + 1 < token.length(); i++) result.add(token.substring(i, i + 2));
        }
        return result;
    }
}
