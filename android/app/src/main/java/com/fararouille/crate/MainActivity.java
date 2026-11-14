package com.fararouille.crate;

import android.Manifest;
import android.annotation.SuppressLint;
import android.app.Activity;
import android.app.DownloadManager;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.PackageManager;
import android.graphics.Color;
import android.graphics.Typeface;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.Environment;
import android.text.InputType;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.view.Window;
import android.webkit.CookieManager;
import android.webkit.DownloadListener;
import android.webkit.URLUtil;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Button;
import android.widget.EditText;
import android.widget.FrameLayout;
import android.widget.LinearLayout;
import android.widget.ProgressBar;
import android.widget.ScrollView;
import android.widget.TextView;
import android.widget.Toast;

import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * Thin Android shell around the crate web app.
 *
 * The library, downloads, and auth all live in crate on the user's own server. This app asks
 * for that server address once, then keeps the web UI in a WebView. Cookies, media playback,
 * and file downloads work exactly as they do in a browser.
 */
public class MainActivity extends Activity {

    private static final String PREFS = "crate";
    private static final String KEY_SERVER = "server";

    private static final int BACKGROUND = Color.rgb(11, 12, 16);
    private static final int PANEL = Color.rgb(18, 20, 26);
    private static final int TEXT = Color.rgb(238, 241, 247);
    private static final int MUTED = Color.rgb(152, 161, 179);
    private static final int FAINT = Color.rgb(107, 116, 134);
    private static final int ACCENT = Color.rgb(139, 92, 246);

    private SharedPreferences prefs;
    private FrameLayout root;
    private WebView webView;
    private ProgressBar progress;
    private View connectView;
    private String serverUrl = "";

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        prefs = getSharedPreferences(PREFS, MODE_PRIVATE);

        root = new FrameLayout(this);
        root.setBackgroundColor(BACKGROUND);
        setContentView(root);

        Window window = getWindow();
        window.setStatusBarColor(BACKGROUND);
        window.setNavigationBarColor(BACKGROUND);

        if (Build.VERSION.SDK_INT >= 33
                && checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS)
                != PackageManager.PERMISSION_GRANTED) {
            requestPermissions(new String[] {Manifest.permission.POST_NOTIFICATIONS}, 1);
        }

        serverUrl = prefs.getString(KEY_SERVER, "");
        if (serverUrl.isEmpty()) {
            showConnect(serverUrl);
        } else {
            openServer(serverUrl);
        }
    }

    // ------------------------------------------------------------- connect UI

    private void showConnect(String current) {
        if (connectView != null) {
            root.removeView(connectView);
        }
        if (webView != null) {
            webView.setVisibility(View.GONE);
        }
        if (progress != null) {
            progress.setVisibility(View.GONE);
        }

        ScrollView scroll = new ScrollView(this);
        scroll.setFillViewport(true);
        scroll.setBackgroundColor(BACKGROUND);

        LinearLayout layout = new LinearLayout(this);
        layout.setOrientation(LinearLayout.VERTICAL);
        layout.setGravity(Gravity.CENTER);
        int pad = dp(28);
        layout.setPadding(pad, pad, pad, pad);
        scroll.addView(
                layout,
                new ScrollView.LayoutParams(
                        ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT));

        TextView logo = new TextView(this);
        logo.setText("crate");
        logo.setTextColor(TEXT);
        logo.setTextSize(36);
        logo.setTypeface(Typeface.DEFAULT_BOLD);
        logo.setGravity(Gravity.CENTER);
        layout.addView(logo, matchWrap());

        TextView intro = new TextView(this);
        intro.setText("Connect to your crate server");
        intro.setTextColor(MUTED);
        intro.setTextSize(14);
        intro.setGravity(Gravity.CENTER);
        LinearLayout.LayoutParams introParams = matchWrap();
        introParams.topMargin = dp(6);
        layout.addView(intro, introParams);

        EditText field = new EditText(this);
        field.setHint("http://192.168.1.42:8000");
        field.setText(current);
        field.setSingleLine(true);
        field.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_URI);
        field.setTextColor(TEXT);
        field.setHintTextColor(FAINT);
        field.setBackgroundColor(PANEL);
        field.setPadding(dp(14), dp(12), dp(14), dp(12));
        LinearLayout.LayoutParams fieldParams = matchWrap();
        fieldParams.topMargin = dp(24);
        layout.addView(field, fieldParams);

        Button button = new Button(this);
        button.setText("Open crate");
        button.setAllCaps(false);
        button.setTextColor(Color.WHITE);
        button.setBackgroundColor(ACCENT);
        LinearLayout.LayoutParams buttonParams = matchWrap();
        buttonParams.topMargin = dp(14);
        buttonParams.height = dp(48);
        layout.addView(button, buttonParams);

        TextView hint = new TextView(this);
        hint.setText(
                "Use the address that crate serve prints, for example http://192.168.1.42:8000."
                        + " Press Back from the library to change it later.");
        hint.setTextColor(MUTED);
        hint.setTextSize(12);
        hint.setGravity(Gravity.CENTER);
        LinearLayout.LayoutParams hintParams = matchWrap();
        hintParams.topMargin = dp(18);
        layout.addView(hint, hintParams);

        button.setOnClickListener(
                view -> {
                    String normalized = normalize(field.getText().toString());
                    if (normalized == null) {
                        Toast.makeText(
                                        this,
                                        "Enter an http:// or https:// server address",
                                        Toast.LENGTH_SHORT)
                                .show();
                        return;
                    }
                    serverUrl = normalized;
                    prefs.edit().putString(KEY_SERVER, normalized).apply();
                    openServer(normalized);
                });

        connectView = scroll;
        root.addView(
                scroll,
                new FrameLayout.LayoutParams(
                        ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT));
        field.requestFocus();
    }

    private String normalize(String raw) {
        String value = raw.trim();
        if (value.isEmpty()) {
            return null;
        }
        if (!value.startsWith("http://") && !value.startsWith("https://")) {
            value = "http://" + value;
        }
        Uri uri = Uri.parse(value);
        if (uri.getHost() == null) {
            return null;
        }
        while (value.endsWith("/")) {
            value = value.substring(0, value.length() - 1);
        }
        return value;
    }

    // ---------------------------------------------------------------- webview

    private void openServer(String url) {
        if (connectView != null) {
            root.removeView(connectView);
            connectView = null;
        }
        if (webView == null) {
            webView = buildWebView();
            root.addView(
                    webView,
                    new FrameLayout.LayoutParams(
                            ViewGroup.LayoutParams.MATCH_PARENT,
                            ViewGroup.LayoutParams.MATCH_PARENT));
            if (progress != null) {
                progress.bringToFront();
            }
        }
        webView.setVisibility(View.VISIBLE);
        webView.loadUrl(url);
    }

    @SuppressLint("SetJavaScriptEnabled")
    private WebView buildWebView() {
        WebView view = new WebView(this);
        view.setBackgroundColor(BACKGROUND);

        WebSettings settings = view.getSettings();
        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true);
        settings.setDatabaseEnabled(true);
        settings.setMediaPlaybackRequiresUserGesture(false);
        settings.setMixedContentMode(WebSettings.MIXED_CONTENT_NEVER_ALLOW);
        settings.setLoadWithOverviewMode(true);
        settings.setUseWideViewPort(true);
        settings.setBuiltInZoomControls(false);
        settings.setDisplayZoomControls(false);
        settings.setUserAgentString(settings.getUserAgentString() + " crate-android/0.1");

        CookieManager cookies = CookieManager.getInstance();
        cookies.setAcceptCookie(true);
        cookies.setAcceptThirdPartyCookies(view, true);

        progress = new ProgressBar(this, null, android.R.attr.progressBarStyleHorizontal);
        progress.setMax(100);
        progress.setVisibility(View.GONE);
        FrameLayout.LayoutParams progressParams =
                new FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(3));
        progressParams.gravity = Gravity.TOP;
        root.addView(progress, progressParams);

        view.setWebViewClient(
                new WebViewClient() {
                    @Override
                    public boolean shouldOverrideUrlLoading(WebView browser, WebResourceRequest request) {
                        return handleUrl(request.getUrl());
                    }

                    @Override
                    public void onPageFinished(WebView browser, String url) {
                        progress.setVisibility(View.GONE);
                    }

                    @Override
                    public void onReceivedError(
                            WebView browser, WebResourceRequest request, WebResourceError error) {
                        if (request.isForMainFrame()) {
                            Toast.makeText(
                                            MainActivity.this,
                                            "Cannot reach the server. Press Back to change the address.",
                                            Toast.LENGTH_LONG)
                                    .show();
                        }
                    }
                });

        view.setWebChromeClient(
                new WebChromeClient() {
                    @Override
                    public void onProgressChanged(WebView browser, int newProgress) {
                        progress.setVisibility(newProgress >= 100 ? View.GONE : View.VISIBLE);
                        progress.setProgress(newProgress);
                    }
                });

        view.setDownloadListener(
                new DownloadListener() {
                    @Override
                    public void onDownloadStart(
                            String url,
                            String userAgent,
                            String contentDisposition,
                            String mimeType,
                            long contentLength) {
                        saveFile(url, contentDisposition, mimeType);
                    }
                });

        return view;
    }

    private boolean handleUrl(Uri uri) {
        String scheme = uri.getScheme();
        if (scheme == null || (!scheme.equals("http") && !scheme.equals("https"))) {
            return true;
        }
        String host = uri.getHost();
        String serverHost = Uri.parse(serverUrl).getHost();
        if (host != null && host.equals(serverHost)) {
            return false;
        }
        try {
            startActivity(new Intent(Intent.ACTION_VIEW, uri));
        } catch (Exception ignored) {
            // No browser available; keep the current page.
        }
        return true;
    }

    /**
     * Work out the saved file name.
     *
     * crate sends ``filename="First Light.mp4"; filename*=UTF-8''First%20Light.mp4``. Android's
     * {@link URLUtil#guessFileName} only understands part of that and falls back to the last URL
     * segment, so every crate download would land as ``file.mp4``. Parse the header here first
     * and keep {@code guessFileName} as the fallback for everything else.
     */
    private String filenameFrom(String url, String contentDisposition, String mimeType) {
        if (contentDisposition != null) {
            Matcher encoded =
                    Pattern.compile("filename\\*=UTF-8''([^;]+)", Pattern.CASE_INSENSITIVE)
                            .matcher(contentDisposition);
            if (encoded.find()) {
                String decoded = Uri.decode(encoded.group(1).trim());
                if (!decoded.isEmpty()) {
                    return decoded;
                }
            }
            Matcher plain =
                    Pattern.compile("filename=\"([^\"]+)\"", Pattern.CASE_INSENSITIVE)
                            .matcher(contentDisposition);
            if (plain.find()) {
                String decoded = plain.group(1).trim();
                if (!decoded.isEmpty()) {
                    return decoded;
                }
            }
        }
        return URLUtil.guessFileName(url, contentDisposition, mimeType);
    }

    private void saveFile(String url, String contentDisposition, String mimeType) {
        try {
            String name = filenameFrom(url, contentDisposition, mimeType);
            name = name.replaceAll("[\\\\/:*?\"<>|]", "_");

            DownloadManager.Request request = new DownloadManager.Request(Uri.parse(url));
            request.setTitle(name);
            request.setDescription("Saved by crate");
            request.setMimeType(mimeType);
            request.setNotificationVisibility(
                    DownloadManager.Request.VISIBILITY_VISIBLE_NOTIFY_COMPLETED);
            request.setDestinationInExternalPublicDir(
                    Environment.DIRECTORY_DOWNLOADS, "crate/" + name);

            String cookie = CookieManager.getInstance().getCookie(url);
            if (cookie != null) {
                request.addRequestHeader("Cookie", cookie);
            }

            DownloadManager manager = (DownloadManager) getSystemService(Context.DOWNLOAD_SERVICE);
            manager.enqueue(request);
            Toast.makeText(this, "Saving to Downloads/crate", Toast.LENGTH_SHORT).show();
        } catch (Exception exception) {
            Toast.makeText(this, "Could not start the download", Toast.LENGTH_SHORT).show();
        }
    }

    // ------------------------------------------------------------ lifecycle

    @Override
    public void onBackPressed() {
        if (webView != null
                && webView.getVisibility() == View.VISIBLE
                && connectView == null) {
            if (webView.canGoBack()) {
                webView.goBack();
            } else {
                showConnect(serverUrl);
            }
            return;
        }
        super.onBackPressed();
    }

    @Override
    protected void onPause() {
        CookieManager.getInstance().flush();
        super.onPause();
    }

    @Override
    protected void onDestroy() {
        if (webView != null) {
            root.removeView(webView);
            webView.destroy();
            webView = null;
        }
        super.onDestroy();
    }

    // --------------------------------------------------------------- helpers

    private LinearLayout.LayoutParams matchWrap() {
        return new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT);
    }

    private int dp(int value) {
        return Math.round(value * getResources().getDisplayMetrics().density);
    }
}
