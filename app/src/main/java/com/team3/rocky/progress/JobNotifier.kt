// AI-generated with Claude Code, 2026-11-11
package com.team3.rocky.progress

import android.Manifest
import android.annotation.SuppressLint
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.pm.PackageManager
import android.os.Build
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import androidx.core.content.ContextCompat
import com.team3.rocky.R
import com.team3.rocky.tr

/**
 * 앱을 보고 있지 않을 때(다른 앱을 쓰는 중) 악보 만들기가 멈추면 휴대폰 알림으로 알려 준다.
 * 알림을 누르면 앱으로 돌아오고, 앱 안에서는 같은 내용이 팝업으로 보인다.
 *
 * 한계: 안드로이드가 앱을 완전히 종료하면 만들던 작업도 함께 사라져서 알림을 보낼 수 없다.
 */
object JobNotifier {
    private const val CHANNEL = "score_jobs"

    /** 안드로이드 13 이상은 사용자가 알림을 허용해야 한다. */
    fun needsPermission(ctx: Context): Boolean =
        Build.VERSION.SDK_INT >= 33 &&
            ContextCompat.checkSelfPermission(ctx, Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED

    private fun ensureChannel(ctx: Context) {
        if (Build.VERSION.SDK_INT < 26) return
        val channel = NotificationChannel(
            CHANNEL, tr("악보 만들기", "Score making"), NotificationManager.IMPORTANCE_HIGH,
        ).apply { description = tr("악보 만들기가 멈췄을 때 알려 줘요", "Tells you when score making stops") }
        ctx.getSystemService(NotificationManager::class.java)?.createNotificationChannel(channel)
    }

    /** 악보 만들기가 멈췄다고 알린다. 알림이 꺼져 있거나 허용되지 않았으면 아무 일도 하지 않는다. */
    @SuppressLint("MissingPermission")   // 바로 아래 needsPermission()에서 확인한다
    fun stopped(ctx: Context, job: ScoreJob, reason: String) {
        val manager = NotificationManagerCompat.from(ctx)
        if (needsPermission(ctx) || !manager.areNotificationsEnabled()) return
        ensureChannel(ctx)
        // 누르면 앱을 다시 앞으로 가져온다.
        val open = ctx.packageManager.getLaunchIntentForPackage(ctx.packageName)?.let {
            PendingIntent.getActivity(ctx, 0, it, PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)
        }
        val note = NotificationCompat.Builder(ctx, CHANNEL)
            .setSmallIcon(R.drawable.ic_stat_rocky)
            .setContentTitle(tr("악보 만들기가 멈췄어요", "Score making stopped"))
            .setContentText("'${job.title}' · $reason")
            .setStyle(NotificationCompat.BigTextStyle().bigText("'${job.title}'\n$reason"))
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .setAutoCancel(true)
            .setContentIntent(open)
            .build()
        // 곡마다 알림 하나. 같은 곡이 다시 멈추면 덮어쓴다.
        try {
            manager.notify((job.id % Int.MAX_VALUE).toInt(), note)
        } catch (e: SecurityException) {
            // 방금 알림 권한이 꺼진 경우. 앱 안 팝업은 그대로 보인다.
        }
    }

    /** 다시 시도하거나 목록에서 지우면 그 곡의 알림을 치운다. */
    fun clear(ctx: Context, job: ScoreJob) {
        NotificationManagerCompat.from(ctx).cancel((job.id % Int.MAX_VALUE).toInt())
    }
}
