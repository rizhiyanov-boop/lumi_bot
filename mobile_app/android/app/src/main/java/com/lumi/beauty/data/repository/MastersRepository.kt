package com.lumi.beauty.data.repository

import com.lumi.beauty.data.api.LumiApi
import com.lumi.beauty.data.model.MasterResponse
import javax.inject.Inject

class MastersRepository @Inject constructor(
    private val api: LumiApi
) {
    suspend fun getMasters(userId: Int = 123456789): List<MasterResponse> {
        return api.getMasters("Bearer $userId")
    }
}

