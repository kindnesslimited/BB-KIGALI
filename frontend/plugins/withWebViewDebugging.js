const { withMainApplication } = require("@expo/config-plugins");

// TEMPORARY DIAGNOSTIC PLUGIN — enables chrome://inspect for the app's
// WebView so we can see live console/network state while debugging the
// "any internal link click hangs" issue. Remove before shipping to stores;
// WebView debugging should not ship in production builds.
module.exports = function withWebViewDebugging(config) {
  return withMainApplication(config, (config) => {
    const isKotlin = config.modResults.language === "kt";
    const importLine = isKotlin
      ? "import android.webkit.WebView"
      : "import android.webkit.WebView;";
    const enableLine = isKotlin
      ? "    WebView.setWebContentsDebuggingEnabled(true)"
      : "    WebView.setWebContentsDebuggingEnabled(true);";

    if (!config.modResults.contents.includes("WebView.setWebContentsDebuggingEnabled")) {
      if (!config.modResults.contents.includes(importLine)) {
        config.modResults.contents = config.modResults.contents.replace(
          /^(package .*\n)/m,
          `$1\n${importLine}\n`
        );
      }
      config.modResults.contents = config.modResults.contents.replace(
        /(super\.onCreate\([^)]*\)\s*\n)/,
        `$1${enableLine}\n`
      );
    }
    return config;
  });
};
