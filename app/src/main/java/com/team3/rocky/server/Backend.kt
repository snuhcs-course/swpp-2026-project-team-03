package com.team3.rocky.server

import android.content.Context
import com.team3.rocky.auth.AccountService
import com.team3.rocky.auth.LocalAccounts
import com.team3.rocky.auth.ServerAccounts
import com.team3.rocky.auth.UserDatabase
import com.team3.rocky.band.BandRepository
import com.team3.rocky.band.LocalBandRepository
import com.team3.rocky.band.ServerBandRepository

/** 회원·밴드를 어디에 저장할지. 앱은 ROCKY 서버를 쓰고, 서버 없이 화면을 시험할 때만 [local]을 켠다. */
object Backend {
    @Volatile var local = false

    fun accounts(ctx: Context): AccountService =
        if (local) LocalAccounts(UserDatabase(ctx)) else ServerAccounts(ctx)

    fun bands(ctx: Context): BandRepository =
        if (local) LocalBandRepository(ctx) else ServerBandRepository(ctx)
}
