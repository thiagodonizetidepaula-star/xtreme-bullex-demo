package com.pocketlens.app;

import java.net.URI;
import java.util.Set;
import java.util.Arrays;
import java.util.HashSet;
import java.util.Collections;

final class WebPolicy {
    static final String PORTAL = "https://pocket-lens-analysis.onrender.com";
    static final Set<String> BROKER_ORIGINS = Collections.unmodifiableSet(new HashSet<>(Arrays.asList("https://pocketoption.com", "https://www.pocketoption.com", "https://m.pocketoption.com")));
    static boolean allowed(String url, boolean broker) {
        try {
            URI uri = URI.create(url);
            if (!"https".equals(uri.getScheme()) || uri.getRawUserInfo() != null || (uri.getPort() != -1 && uri.getPort() != 443)) return false;
            String origin = "https://" + uri.getHost();
            return broker ? BROKER_ORIGINS.contains(origin) : PORTAL.equals(origin);
        } catch (Exception ignored) { return false; }
    }
}
