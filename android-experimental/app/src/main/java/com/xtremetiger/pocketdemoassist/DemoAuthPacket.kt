package com.xtremetiger.pocketdemoassist

import org.json.JSONArray

/**
 * Strict demo-only validation before even holding a third-party auth token in memory.
 * This does NOT prove that a session is valid with the broker.
 */
object DemoAuthPacket {
    fun validate(packet: String?): String? {
        if (packet == null || packet.length > 17000 || !packet.startsWith("42")) return null
        return try {
            val pair = JSONArray(packet.substring(2))
            if (pair.length() != 2 || pair.optString(0) != "auth") return null
            val data = pair.optJSONObject(1) ?: return null
            if (!data.has("isDemo") || data.opt("isDemo") !is Int || data.getInt("isDemo") != 1) return null
            val session = data.optString("session")
            if (session.length !in 10..16000) return null
            if (!data.has("uid") || data.opt("uid") !is Number || data.getLong("uid") <= 0L) return null
            packet
        } catch (_: Exception) {
            null
        }
    }
}
