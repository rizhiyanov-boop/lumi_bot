package com.lumi.beauty.data.api

import com.lumi.beauty.data.model.*
import retrofit2.http.*

interface LumiApi {
    
    @GET("api/masters")
    suspend fun getMasters(
        @Header("Authorization") token: String
    ): List<MasterResponse>
    
    @GET("api/masters/{masterId}")
    suspend fun getMasterDetail(
        @Path("masterId") masterId: Int,
        @Header("Authorization") token: String
    ): MasterDetailResponse
    
    @GET("api/masters/{masterId}/services/{serviceId}/time-slots")
    suspend fun getTimeSlots(
        @Path("masterId") masterId: Int,
        @Path("serviceId") serviceId: Int,
        @Query("date_from") dateFrom: String,
        @Query("date_to") dateTo: String,
        @Header("Authorization") token: String
    ): List<TimeSlotResponse>
    
    @POST("api/bookings")
    suspend fun createBooking(
        @Body request: BookingRequest,
        @Header("Authorization") token: String
    ): BookingResponse
    
    @GET("api/bookings")
    suspend fun getBookings(
        @Header("Authorization") token: String
    ): List<BookingResponse>
    
    @POST("api/masters/{masterId}/add")
    suspend fun addMaster(
        @Path("masterId") masterId: Int,
        @Header("Authorization") token: String
    ): ApiResponse
    
    @DELETE("api/masters/{masterId}/remove")
    suspend fun removeMaster(
        @Path("masterId") masterId: Int,
        @Header("Authorization") token: String
    ): ApiResponse
    
    @GET("api/cities")
    suspend fun getCities(): List<CityResponse>
    
    @GET("api/cities/{cityId}/masters")
    suspend fun getCityMasters(
        @Path("cityId") cityId: Int,
        @Header("Authorization") token: String
    ): List<MasterResponse>
}

