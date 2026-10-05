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
import android.webkit.WebSettings
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.ProgressBar
import android.widget.TextView
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
                errorPanel.visibility = View.GONE
                webView.visibility = View.VISIBLE
            }

            override fun onReceivedError(
                view: WebView?,
                request: WebResourceRequest?,
                error: WebResourceError?
            ) {
                if (request?.isForMainFrame == true) {
                    showError(
                        getString(
                            R.string.error_load,
                            Prefs.getServerUrl(this@MainActivity),
                            error?.description?.toString().orEmpty()
                        )
                    )
                }
            }

            override fun shouldOverrideUrlLoading(
                view: WebView?,
                request: WebResourceRequest?
            ): Boolean = false
        }

        if (!Prefs.isFirstRunDone(this)) {
            showFirstRunDialog()
        } else {
            loadMonitor()
        }
    }

    private fun showFirstRunDialog() {
        val input = layoutInflater.inflate(R.layout.dialog_server_url, null)
        val edit = input.findViewById<com.google.android.material.textfield.TextInputEditText>(R.id.inputUrl)
        edit.setText(Prefs.getServerUrl(this))

        AlertDialog.Builder(this)
            .setTitle(R.string.first_run_title)
            .setMessage(R.string.first_run_message)
            .setView(input)
            .setCancelable(false)
            .setPositiveButton(R.string.save) { _, _ ->
                Prefs.setServerUrl(this, edit.text?.toString().orEmpty())
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
        errorPanel.visibility = View.GONE
        webView.visibility = View.VISIBLE
        webView.loadUrl(url)
        supportActionBar?.subtitle = url
    }

    private fun showError(message: String) {
        webView.visibility = View.GONE
        errorPanel.visibility = View.VISIBLE
        errorText.text = message
    }

    private fun openSettings() {
        startActivity(Intent(this, SettingsActivity::class.java))
    }

    override fun onResume() {
        super.onResume()
        if (Prefs.isFirstRunDone(this)) {
            val current = webView.url
            val wanted = Prefs.getServerUrl(this)
            if (current == null || !current.startsWith(wanted)) {
                loadMonitor()
            }
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

    @Deprecated("Deprecated in Java")
    override fun onBackPressed() {
        if (webView.canGoBack()) {
            webView.goBack()
        } else {
            @Suppress("DEPRECATION")
            super.onBackPressed()
        }
    }
}
