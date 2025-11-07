package com.lumi.beauty.ui.screens.masterdetail

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun MasterDetailScreen(
    masterId: Int,
    onBack: () -> Unit,
    onBookClick: (Int, Int) -> Unit
) {
    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Мастер") },
                navigationIcon = {
                    TextButton(onClick = onBack) {
                        Text("Назад")
                    }
                }
            )
        }
    ) { padding ->
        LazyColumn(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding),
            contentPadding = PaddingValues(16.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp)
        ) {
            item {
                Text("Детали мастера #$masterId")
            }
        }
    }
}

