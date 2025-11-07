package com.lumi.beauty.data.model

import com.google.gson.annotations.SerializedName

data class MasterResponse(
    val id: Int,
    val name: String,
    val description: String?,
    @SerializedName("avatar_url") val avatarUrl: String?,
    @SerializedName("city_name") val cityName: String?,
    @SerializedName("services_count") val servicesCount: Int
)

data class ServiceResponse(
    val id: Int,
    val title: String,
    val description: String?,
    val price: Double,
    @SerializedName("duration_mins") val durationMins: Int,
    @SerializedName("category_name") val categoryName: String?,
    @SerializedName("portfolio_photos") val portfolioPhotos: List<String>
)

data class MasterDetailResponse(
    val id: Int,
    val name: String,
    val description: String?,
    @SerializedName("avatar_url") val avatarUrl: String?,
    val city: String?,
    val services: List<ServiceResponse>,
    @SerializedName("work_schedule") val workSchedule: List<Map<String, Any>>
)

// WorkPeriod теперь часть MasterDetailResponse как Map

data class TimeSlotResponse(
    val date: String,
    val time: String,
    val available: Boolean
)

data class BookingRequest(
    @SerializedName("master_id") val masterId: Int,
    @SerializedName("service_id") val serviceId: Int,
    @SerializedName("start_datetime") val startDatetime: String,
    val comment: String? = null
)

data class BookingResponse(
    val id: Int,
    @SerializedName("master_name") val masterName: String,
    @SerializedName("service_title") val serviceTitle: String,
    @SerializedName("start_datetime") val startDatetime: String,
    @SerializedName("end_datetime") val endDatetime: String,
    val price: Double,
    val status: String
)

data class CityResponse(
    val id: Int,
    @SerializedName("name_ru") val nameRu: String,
    @SerializedName("name_local") val nameLocal: String,
    @SerializedName("name_en") val nameEn: String
)

data class ApiResponse(
    val success: Boolean,
    val message: String
)

