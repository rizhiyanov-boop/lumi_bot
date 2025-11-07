package com.lumi.beauty.di

import com.lumi.beauty.data.api.LumiApi
import dagger.Module
import dagger.Provides
import dagger.hilt.InstallIn
import dagger.hilt.components.SingletonComponent
import okhttp3.OkHttpClient
import okhttp3.logging.HttpLoggingInterceptor
import retrofit2.Retrofit
import retrofit2.converter.gson.GsonConverterFactory
import javax.inject.Singleton

@Module
@InstallIn(SingletonComponent::class)
object AppModule {
    
    @Provides
    @Singleton
    fun provideOkHttpClient(): OkHttpClient {
        val logging = HttpLoggingInterceptor()
        logging.level = HttpLoggingInterceptor.Level.BODY
        
        return OkHttpClient.Builder()
            .addInterceptor(logging)
            .build()
    }
    
    @Provides
    @Singleton
    fun provideRetrofit(okHttpClient: OkHttpClient): Retrofit {
        // В продакшене брать из BuildConfig или local.properties
        // Для эмулятора: http://10.0.2.2:8000/
        // Для реального устройства: http://YOUR_COMPUTER_IP:8000/
        val baseUrl = "http://10.0.2.2:8000/" // Android emulator localhost
        
        return Retrofit.Builder()
            .baseUrl(baseUrl)
            .client(okHttpClient)
            .addConverterFactory(GsonConverterFactory.create())
            .build()
    }
    
    @Provides
    @Singleton
    fun provideLumiApi(retrofit: Retrofit): LumiApi {
        return retrofit.create(LumiApi::class.java)
    }
}

