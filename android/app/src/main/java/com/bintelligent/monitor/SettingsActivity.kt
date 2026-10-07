package com.bintelligent.monitor

import android.os.Bundle
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import com.google.android.material.appbar.MaterialToolbar
import com.google.android.material.button.MaterialButton
import com.google.android.material.textfield.TextInputEditText

class SettingsActivity : AppCompatActivity() {

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_settings)

        val toolbar = findViewById<MaterialToolbar>(R.id.toolbar)
        setSupportActionBar(toolbar)
        supportActionBar?.setDisplayHomeAsUpEnabled(true)
        toolbar.setNavigationOnClickListener { finish() }

        val edit = findViewById<TextInputEditText>(R.id.inputUrl)
        edit.setText(Prefs.getServerUrl(this))

        findViewById<MaterialButton>(R.id.btnSave).setOnClickListener {
            val raw = edit.text?.toString().orEmpty()
            if (!Prefs.isValidServerUrl(raw)) {
                Toast.makeText(this, R.string.error_invalid_url, Toast.LENGTH_LONG).show()
                return@setOnClickListener
            }
            Prefs.setServerUrl(this, raw)
            Prefs.setFirstRunDone(this)
            Toast.makeText(this, R.string.url_saved, Toast.LENGTH_SHORT).show()
            finish()
        }

        findViewById<MaterialButton>(R.id.btnDemo).setOnClickListener {
            edit.setText(Prefs.DEMO_URL)
        }

        findViewById<MaterialButton>(R.id.btnHint).setOnClickListener {
            edit.setText(Prefs.DEFAULT_HINT_URL)
        }
    }
}
