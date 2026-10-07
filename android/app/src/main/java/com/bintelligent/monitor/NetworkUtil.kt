package com.bintelligent.monitor

import android.content.Context
import android.net.ConnectivityManager
import android.net.NetworkCapabilities

object NetworkUtil {
    enum class Status {
        WIFI_OR_ETHERNET,
        CELLULAR_ONLY,
        OFFLINE
    }

    fun status(context: Context): Status {
        val cm = context.getSystemService(Context.CONNECTIVITY_SERVICE) as? ConnectivityManager
            ?: return Status.OFFLINE
        val network = cm.activeNetwork ?: return Status.OFFLINE
        val caps = cm.getNetworkCapabilities(network) ?: return Status.OFFLINE

        val wifi = caps.hasTransport(NetworkCapabilities.TRANSPORT_WIFI)
        val ethernet = caps.hasTransport(NetworkCapabilities.TRANSPORT_ETHERNET)
        val cellular = caps.hasTransport(NetworkCapabilities.TRANSPORT_CELLULAR)

        return when {
            wifi || ethernet -> Status.WIFI_OR_ETHERNET
            cellular -> Status.CELLULAR_ONLY
            else -> Status.OFFLINE
        }
    }
}
