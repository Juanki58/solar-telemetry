package com.bintelligent.monitor

import android.annotation.SuppressLint
import android.content.Intent
import android.graphics.Bitmap
import android.os.Bundle
import android.view.Menu
import android.view.MenuItem
import android.view.View
import android.webkit.WebChromeClient
import android.webkit.WebResourceError
import android.webkit.WebResourceRequest
import android.webkit.WebResourceResponse
import android.webkit.WebSettings
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.ProgressBar
import android.widget.TextView
import androidx.activity.OnBackPressedCallback
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import com.google.android.material.appbar.MaterialToolbar
import com.google.android.material.button.MaterialButton

class MainActivity : AppCompatActivity() {

    private lateinit var webView: WebView
    private lateinit var progress: ProgressBar
    private lateinit var errorPanel: View
    private lateinit var errorText: TextView

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        val toolbar = findViewById<MaterialToolbar>(R.id.toolbar)
        setSupportActionBar(toolbar)

        webView = findViewById(R.id.webView)
        progress = findViewById(R.id.progress)
        errorPanel = findViewById(R.id.errorPanel)
        errorText = findViewById(R.id.errorText)

        findViewById<MaterialButton>(R.id.btnRetry).setOnClickListener { loadMonitor() }
        findViewById<MaterialButton>(R.id.btnSettings).setOnClickListener { openSettings() }

        val settings = webView.settings
        settings.javaScriptEnabled = true
        settings.domStorageEnabled = true
        settings.cacheMode = WebSettings.LOAD_DEFAULT
        settings.mixedContentMode = WebSettings.MIXED_CONTENT_COMPATIBILITY_MODE
        settings.builtInZoomControls = true
        settings.displayZoomControls = false
        settings.loadWithOverviewMode = true
        settings.useWideViewPort = true

        webView.webChromeClient = object : WebChromeClient() {
            override fun onProgressChanged(view: WebView?, newProgress: Int) {
                progress.visibility = if (newProgress in 1..99) View.VISIBLE else View.GONE
                progress.progress = newProgress
            }
        }

        webView.webViewClient = object : WebViewClient() {
            override fun onPageStarted(view: WebView?, url: String?, favicon: Bitmap?) {
                if (url != null && url != "about:blank") {
                    errorPanel.visibility = View.GONE
                    webView.visibility = View.VISIBLE
                }
            }

            override fun onReceivedError(
                view: WebView?,
                request: WebResourceRequest?,
                error: WebResourceError?
            ) {
                if (request?.isForMainFrame != true) return
                val desc = error?.description?.toString().orEmpty()
                val code = error?.errorCode ?: 0
                showError(humanizeLoadError(desc, code))
                view?.stopLoading()
                view?.loadUrl("about:blank")
            }

            override fun onReceivedHttpError(
                view: WebView?,
                request: WebResourceRequest?,
                errorResponse: WebResourceResponse?
            ) {
                if (request?.isForMainFrame != true) return
                val code = errorResponse?.statusCode ?: 0
                if (code in 400..599) {
                    showError(
                        getString(
                            R.string.error_http,
                            Prefs.getServerUrl(this@MainActivity),
                            code
                        )
                    )
                    view?.stopLoading()
                    view?.loadUrl("about:blank")
                }
            }

            override fun shouldOverrideUrlLoading(
                view: WebView?,
                request: WebResourceRequest?
            ): Boolean = false
        }

        onBackPressedDispatcher.addCallback(
            this,
            object : OnBackPressedCallback(true) {
                override fun handleOnBackPressed() {
                    if (webView.visibility == View.VISIBLE && webView.canGoBack()) {
                        webView.goBack()
                    } else {
                        isEnabled = false
                        onBackPressedDispatcher.onBackPressed()
                        isEnabled = true
                    }
                }
            }
        )

        if (!Prefs.isFirstRunDone(this)) {
            showFirstRunDialog()
        } else {
            loadMonitor()
        }
    }

    private fun showFirstRunDialog() {
        val input = layoutInflater.inflate(R.layout.dialog_server_url, null)
        val edit = input.findViewById<com.google.android.material.textfield.TextInputEditText>(R.id.inputUrl)
        edit.setText(Prefs.DEFAULT_HINT_URL)
        edit.hint = Prefs.DEFAULT_HINT_URL

        AlertDialog.Builder(this)
            .setTitle(R.string.first_run_title)
            .setMessage(R.string.first_run_message)
            .setView(input)
            .setCancelable(false)
            .setPositiveButton(R.string.save) { _, _ ->
                val raw = edit.text?.toString().orEmpty()
                if (!Prefs.isValidServerUrl(raw)) {
                    Prefs.setServerUrl(this, Prefs.DEFAULT_HINT_URL)
                } else {
                    Prefs.setServerUrl(this, raw)
                }
                Prefs.setFirstRunDone(this)
                loadMonitor()
            }
            .setNeutralButton(R.string.use_demo) { _, _ ->
                Prefs.setServerUrl(this, Prefs.DEMO_URL)
                Prefs.setFirstRunDone(this)
                loadMonitor()
            }
            .show()
    }

    private fun loadMonitor() {
        val url = Prefs.getServerUrl(this)
        supportActionBar?.subtitle = url

        if (!Prefs.isValidServerUrl(url)) {
            showError(getString(R.string.error_bad_url, url))
            return
        }

        when (NetworkUtil.status(this)) {
            NetworkUtil.Status.OFFLINE -> {
                showError(getString(R.string.error_offline, url))
                return
            }
            NetworkUtil.Status.CELLULAR_ONLY -> {
                // Still try — some users tether — but explain if it fails.
            }
            NetworkUtil.Status.WIFI_OR_ETHERNET -> Unit
        }

        errorPanel.visibility = View.GONE
        webView.visibility = View.VISIBLE
        webView.loadUrl(url)
    }

    private fun humanizeLoadError(description: String, errorCode: Int): String {
        val url = Prefs.getServerUrl(this)
        val lower = description.lowercase()
        val detail = when {
            NetworkUtil.status(this) == NetworkUtil.Status.OFFLINE ->
                getString(R.string.error_reason_offline)
            NetworkUtil.status(this) == NetworkUtil.Status.CELLULAR_ONLY ->
                getString(R.string.error_reason_cellular)
            errorCode == WebViewClient.ERROR_HOST_LOOKUP ||
                lower.contains("err_name_not_resolved") ||
                lower.contains("hostname") ->
                getString(R.string.error_reason_host)
            errorCode == WebViewClient.ERROR_CONNECT ||
                lower.contains("err_connection_refused") ||
                lower.contains("refused") ->
                getString(R.string.error_reason_refused)
            errorCode == WebViewClient.ERROR_TIMEOUT ||
                lower.contains("timed out") ||
                lower.contains("timeout") ->
                getString(R.string.error_reason_timeout)
            errorCode == WebViewClient.ERROR_IO ||
                lower.contains("err_address_unreachable") ||
                lower.contains("unreachable") ->
                getString(R.string.error_reason_unreachable)
            description.isNotBlank() -> description
            else -> getString(R.string.error_reason_generic)
        }
        return getString(R.string.error_load, url, detail)
    }

    private fun showError(message: String) {
        progress.visibility = View.GONE
        webView.visibility = View.GONE
        errorPanel.visibility = View.VISIBLE
        errorText.text = message
    }

    private fun openSettings() {
        startActivity(Intent(this, SettingsActivity::class.java))
    }

    override fun onResume() {
        super.onResume()
        if (!Prefs.isFirstRunDone(this)) return
        val wanted = Prefs.getServerUrl(this)
        val current = webView.url
        val showingError = errorPanel.visibility == View.VISIBLE
        // Reconnect after settings, first paint, or if the WebView was cleared on error.
        if (showingError || current == null || current == "about:blank" || !current.startsWith(wanted)) {
            loadMonitor()
        }
    }

    override fun onCreateOptionsMenu(menu: Menu): Boolean {
        menuInflater.inflate(R.menu.main_menu, menu)
        return true
    }

    override fun onOptionsItemSelected(item: MenuItem): Boolean = when (item.itemId) {
        R.id.action_refresh -> {
            loadMonitor()
            true
        }
        R.id.action_settings -> {
            openSettings()
            true
        }
        R.id.action_demo -> {
            Prefs.setServerUrl(this, Prefs.DEMO_URL)
            loadMonitor()
            true
        }
        else -> super.onOptionsItemSelected(item)
    }
}
