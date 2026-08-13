package com.cryptosentinelai.app;

import android.app.DownloadManager;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.net.Uri;
import android.os.Build;
import android.os.Environment;
import android.provider.Settings;
import com.getcapacitor.JSObject;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;

@CapacitorPlugin(name = "AppSettings")
public class AppSettingsPlugin extends Plugin {

    @PluginMethod
    public void openNotifications(PluginCall call) {
        Intent intent = new Intent(Settings.ACTION_APP_NOTIFICATION_SETTINGS);
        intent.putExtra(Settings.EXTRA_APP_PACKAGE, getContext().getPackageName());
        getActivity().startActivity(intent);
        call.resolve();
    }

    @PluginMethod
    public void openBatterySettings(PluginCall call) {
        try {
            String pkg = getContext().getPackageName();
            Intent intent = new Intent(Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS);
            intent.setData(Uri.parse("package:" + pkg));
            getActivity().startActivity(intent);
            call.resolve();
        } catch (Exception e) {
            try {
                Intent fallback = new Intent(Settings.ACTION_IGNORE_BATTERY_OPTIMIZATION_SETTINGS);
                getActivity().startActivity(fallback);
                call.resolve();
            } catch (Exception e2) {
                call.reject("Impossibile aprire le impostazioni risparmio energetico");
            }
        }
    }

    @PluginMethod
    public void downloadApk(PluginCall call) {
        String url = call.getString("url");
        if (url == null) { call.reject("url mancante"); return; }

        DownloadManager dm = (DownloadManager) getContext()
            .getSystemService(Context.DOWNLOAD_SERVICE);

        DownloadManager.Request request = new DownloadManager.Request(Uri.parse(url));
        request.setTitle("CryptoSentinel");
        request.setDescription("Download aggiornamento in corso...");
        request.setNotificationVisibility(
            DownloadManager.Request.VISIBILITY_VISIBLE_NOTIFY_COMPLETED
        );
        request.setDestinationInExternalPublicDir(
            Environment.DIRECTORY_DOWNLOADS, "CryptoSentinel-update.apk"
        );
        request.setMimeType("application/vnd.android.package-archive");

        long downloadId = dm.enqueue(request);

        BroadcastReceiver receiver = new BroadcastReceiver() {
            @Override
            public void onReceive(Context ctx, Intent intent) {
                long id = intent.getLongExtra(DownloadManager.EXTRA_DOWNLOAD_ID, -1);
                if (id != downloadId) return;
                ctx.unregisterReceiver(this);

                // Check actual download status
                DownloadManager.Query query = new DownloadManager.Query();
                query.setFilterById(downloadId);
                android.database.Cursor cursor = dm.query(query);
                int status = DownloadManager.STATUS_FAILED;
                String reason = "unknown";
                if (cursor != null && cursor.moveToFirst()) {
                    int statusIdx = cursor.getColumnIndex(DownloadManager.COLUMN_STATUS);
                    int reasonIdx = cursor.getColumnIndex(DownloadManager.COLUMN_REASON);
                    if (statusIdx >= 0) status = cursor.getInt(statusIdx);
                    if (reasonIdx >= 0) reason = String.valueOf(cursor.getInt(reasonIdx));
                    cursor.close();
                }

                JSObject data = new JSObject();
                if (status == DownloadManager.STATUS_SUCCESSFUL) {
                    data.put("status", "completed");
                    notifyListeners("downloadComplete", data);
                    Uri apkUri = dm.getUriForDownloadedFile(downloadId);
                    if (apkUri == null) return;
                    Intent install = new Intent(Intent.ACTION_VIEW);
                    install.setDataAndType(apkUri, "application/vnd.android.package-archive");
                    install.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
                    install.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);
                    ctx.startActivity(install);
                } else {
                    data.put("status", "failed");
                    data.put("reason", reason);
                    notifyListeners("downloadComplete", data);
                }
            }
        };

        IntentFilter filter = new IntentFilter(DownloadManager.ACTION_DOWNLOAD_COMPLETE);
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            // RECEIVER_EXPORTED required: ACTION_DOWNLOAD_COMPLETE is sent by system DownloadManager
            getContext().registerReceiver(receiver, filter, Context.RECEIVER_EXPORTED);
        } else {
            getContext().registerReceiver(receiver, filter);
        }

        call.resolve();
    }

    @PluginMethod
    public void openDownloads(PluginCall call) {
        Intent intent = new Intent(DownloadManager.ACTION_VIEW_DOWNLOADS);
        intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
        getContext().startActivity(intent);
        call.resolve();
    }

    @PluginMethod
    public void getAlerts(PluginCall call) {
        String json = getContext()
            .getSharedPreferences("cryptosentinel_prefs", android.content.Context.MODE_PRIVATE)
            .getString("alerts_json", "[]");
        JSObject result = new JSObject();
        result.put("json", json);
        call.resolve(result);
    }

    @PluginMethod
    public void getRangeAlerts(PluginCall call) {
        String json = getContext()
            .getSharedPreferences("cryptosentinel_prefs", android.content.Context.MODE_PRIVATE)
            .getString("range_alerts_json", "[]");
        JSObject result = new JSObject();
        result.put("json", json);
        call.resolve(result);
    }

    @PluginMethod
    public void syncRangeAlerts(PluginCall call) {
        String json = call.getString("json", "[]");
        getContext().getSharedPreferences("cryptosentinel_prefs", android.content.Context.MODE_PRIVATE)
            .edit().putString("range_alerts_json", json).apply();
        call.resolve();
    }

    @PluginMethod
    public void syncAlerts(PluginCall call) {
        String json = call.getString("json", "[]");
        getContext().getSharedPreferences("cryptosentinel_prefs", android.content.Context.MODE_PRIVATE)
            .edit().putString("alerts_json", json).apply();
        call.resolve();
    }

    @PluginMethod
    public void syncFavAlerts(PluginCall call) {
        String coinsJson     = call.getString("coinsJson", "[]");
        float  upPct         = call.getFloat("upPct",   0f);
        float  downPct       = call.getFloat("downPct", 0f);
        String refPricesJson = call.getString("refPricesJson", "{}");
        String currency      = call.getString("currency", "usd");
        android.content.SharedPreferences.Editor ed = getContext()
            .getSharedPreferences("cryptosentinel_prefs", android.content.Context.MODE_PRIVATE)
            .edit()
            .putString("fav_coins_json", coinsJson)
            .putFloat("fav_up_pct",   upPct)
            .putFloat("fav_down_pct", downPct)
            .putString("fav_currency", currency);
        if (refPricesJson != null && !refPricesJson.equals("{}") && !refPricesJson.isEmpty()) {
            ed.putString("fav_ref_prices", refPricesJson);
        }
        ed.apply();
        call.resolve();
    }

    @PluginMethod
    public void getAndClearPendingFavAlerts(PluginCall call) {
        android.content.SharedPreferences prefs = getContext()
            .getSharedPreferences("cryptosentinel_prefs", android.content.Context.MODE_PRIVATE);
        String json = prefs.getString("pending_fav_alerts_json", "[]");
        prefs.edit().putString("pending_fav_alerts_json", "[]").apply();
        JSObject result = new JSObject();
        result.put("json", json);
        call.resolve(result);
    }

    @PluginMethod
    public void openWithChooser(PluginCall call) {
        String url = call.getString("url");
        if (url == null) { call.reject("url mancante"); return; }
        String title = call.getString("title", "Apri con");
        Intent view = new Intent(Intent.ACTION_VIEW, Uri.parse(url));
        Intent chooser = Intent.createChooser(view, title);
        chooser.setFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
        getContext().startActivity(chooser);
        call.resolve();
    }
}
