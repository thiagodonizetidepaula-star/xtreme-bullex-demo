package com.xtremetiger.pocketdemoassist

import org.junit.Assert.*
import org.junit.Test

class DemoAuthPacketTest {
    private fun packet(mode: String) = """42["auth",{"session":"demo-session-123456","uid":123,"isDemo":$mode}]"""
    @Test fun acceptsExplicitDemo() {
        assertEquals(packet("1"), DemoAuthPacket.validate(packet("1")))
    }
    @Test fun rejectsRealAndUnknown() {
        for (mode in listOf("0", "true", "\"1\"", "null")) {
            assertNull(DemoAuthPacket.validate(packet(mode)))
        }
    }
    @Test fun rejectsWrongEventAndBadPacket() {
        assertNull(DemoAuthPacket.validate("""42["order",{"session":"demo-session-123456","uid":123,"isDemo":1}]"""))
        assertNull(DemoAuthPacket.validate("42not-json"))
        assertNull(DemoAuthPacket.validate("""42["auth",{"session":"short","uid":123,"isDemo":1}]"""))
        assertNull(DemoAuthPacket.validate(null))
    }
}
