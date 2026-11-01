package com.pocketlens.app;
import org.junit.Test;
import static org.junit.Assert.*;
public class WebPolicyTest {
    @Test public void portalIsExactHttpsOrigin(){
        assertTrue(WebPolicy.allowed("https://pocket-lens-analysis.onrender.com/",false));
        assertFalse(WebPolicy.allowed("http://pocket-lens-analysis.onrender.com/",false));
        assertFalse(WebPolicy.allowed("https://pocket-lens-analysis.onrender.com.evil.example/",false));
        assertFalse(WebPolicy.allowed("https://pocket-lens-analysis.onrender.com@evil.example/",false));
        assertFalse(WebPolicy.allowed("https://pocket-lens-analysis.onrender.com:8443/",false));
    }
    @Test public void brokerOriginsAreExplicit(){
        assertTrue(WebPolicy.allowed("https://m.pocketoption.com/pt/login/",true));
        assertTrue(WebPolicy.allowed("https://pocketoption.com/en/cabinet/demo-quick-high-low/",true));
        assertFalse(WebPolicy.allowed("https://pocketoption.com.evil.example/",true));
        assertFalse(WebPolicy.allowed("https://evil.pocketoption.com/",true));
        assertFalse(WebPolicy.allowed("javascript:alert(1)",true));
        assertFalse(WebPolicy.allowed("file:///etc/passwd",true));
    }
}
