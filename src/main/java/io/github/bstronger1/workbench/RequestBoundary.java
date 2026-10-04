package io.github.bstronger1.workbench;

import jakarta.servlet.*;
import jakarta.servlet.http.*;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;
import java.io.*;

/** Bound JSON bodies even when the client uses chunked transfer encoding. */
@Component
public class RequestBoundary extends OncePerRequestFilter {
    @Override protected void doFilterInternal(HttpServletRequest req, HttpServletResponse res, FilterChain chain) throws ServletException, IOException {
        res.setHeader("X-Content-Type-Options", "nosniff");
        res.setHeader("Referrer-Policy", "no-referrer");
        if (!req.getRequestURI().startsWith("/api/")) { chain.doFilter(req,res); return; }
        res.setHeader("Cache-Control", "no-store");
        if (!req.getMethod().equals("POST")) { chain.doFilter(req,res); return; }
        byte[] bytes = req.getInputStream().readNBytes(131073);
        if (bytes.length > 131072) { res.setStatus(413);res.setContentType("application/json");res.getWriter().write("{\"message\":\"Request body too large\"}");return; }
        chain.doFilter(new HttpServletRequestWrapper(req) {
            @Override public ServletInputStream getInputStream() {
                ByteArrayInputStream stream = new ByteArrayInputStream(bytes);
                return new ServletInputStream() {
                    @Override public int read() { return stream.read(); }
                    @Override public int read(byte[] b,int off,int len) { return stream.read(b,off,len); }
                    @Override public boolean isFinished() { return stream.available()==0; }
                    @Override public boolean isReady() { return true; }
                    @Override public void setReadListener(ReadListener listener) { throw new UnsupportedOperationException(); }
                };
            }
            @Override public BufferedReader getReader() { return new BufferedReader(new InputStreamReader(getInputStream(),java.nio.charset.StandardCharsets.UTF_8)); }
        },res);
    }
}
