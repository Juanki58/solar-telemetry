package com.bintelligent.monitor

import android.content.Context
import android.content.SharedPreferences
import androidx.core.content.edit

object Prefs {
    const val PREFS_NAME = "bintelligent_monitor"
    const val KEY_SERVER_URL = "server_url"
    const val KEY_FIRST_RUN = "first_run_done"

    /** Hint shown in settings; user must replace with their PC LAN IP. */
    const val DEFAULT_HINT_URL = "http://192.168.1.100:8501"
    const val DEMO_URL =
        "https://htmlpreview.github.io/?https://github.com/Juanki58/solar-telemetry/blob/main/docs/index.html"

    fun prefs(context: Context): SharedPreferences =
        context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)

    fun getServerUrl(context: Context): String =
        prefs(context).getString(KEY_SERVER_URL, DEFAULT_HINT_URL)?.trim().orEmpty()
            .ifEmpty { DEFAULT_HINT_URL }

    fun setServerUrl(context: Context, url: String) {
        prefs(context).edit {
            putString(KEY_SERVER_URL, normalizeUrl(url))
        }
    }

    fun isFirstRunDone(context: Context): Boolean =
        prefs(context).getBoolean(KEY_FIRST_RUN, false)

    fun setFirstRunDone(context: Context) {
        prefs(context).edit { putBoolean(KEY_FIRST_RUN, true) }
    }

    fun normalizeUrl(raw: String): String {
        var u = raw.trim()
        if (u.isEmpty()) return DEFAULT_HINT_URL
        if (!u.startsWith("http://") && !u.startsWith("https://")) {
            u = "http://$u"
        }
        return u.trimEnd('/')
    }
}
