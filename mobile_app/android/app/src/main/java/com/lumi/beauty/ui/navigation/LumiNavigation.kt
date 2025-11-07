package com.lumi.beauty.ui.navigation

import androidx.compose.runtime.Composable
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController
import com.lumi.beauty.ui.screens.bookings.BookingsScreen
import com.lumi.beauty.ui.screens.masters.MastersScreen
import com.lumi.beauty.ui.screens.masterdetail.MasterDetailScreen
import com.lumi.beauty.ui.screens.search.SearchScreen

@Composable
fun LumiNavigation() {
    val navController = rememberNavController()
    
    NavHost(
        navController = navController,
        startDestination = "masters"
    ) {
        composable("masters") {
            MastersScreen(
                onMasterClick = { masterId ->
                    navController.navigate("master_detail/$masterId")
                },
                onSearchClick = {
                    navController.navigate("search")
                }
            )
        }
        
        composable("master_detail/{masterId}") { backStackEntry ->
            val masterId = backStackEntry.arguments?.getString("masterId")?.toIntOrNull() ?: return@composable
            MasterDetailScreen(
                masterId = masterId,
                onBack = { navController.popBackStack() },
                onBookClick = { masterId, serviceId ->
                    // Navigate to booking screen
                }
            )
        }
        
        composable("search") {
            SearchScreen(
                onBack = { navController.popBackStack() },
                onMasterClick = { masterId ->
                    navController.navigate("master_detail/$masterId") {
                        popUpTo("masters")
                    }
                }
            )
        }
        
        composable("bookings") {
            BookingsScreen()
        }
    }
}

