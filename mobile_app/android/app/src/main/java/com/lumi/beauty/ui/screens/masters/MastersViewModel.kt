package com.lumi.beauty.ui.screens.masters

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.lumi.beauty.data.model.MasterResponse
import com.lumi.beauty.data.repository.MastersRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import javax.inject.Inject

data class MastersUiState(
    val masters: List<MasterResponse> = emptyList(),
    val isLoading: Boolean = false,
    val error: String? = null
)

@HiltViewModel
class MastersViewModel @Inject constructor(
    private val repository: MastersRepository
) : ViewModel() {
    
    private val _uiState = MutableStateFlow(MastersUiState())
    val uiState: StateFlow<MastersUiState> = _uiState.asStateFlow()
    
    init {
        loadMasters()
    }
    
    fun loadMasters(userId: Int = 123456789) {
        viewModelScope.launch {
            _uiState.value = _uiState.value.copy(isLoading = true, error = null)
            try {
                val masters = repository.getMasters(userId)
                _uiState.value = _uiState.value.copy(
                    masters = masters,
                    isLoading = false
                )
            } catch (e: Exception) {
                _uiState.value = _uiState.value.copy(
                    isLoading = false,
                    error = e.message ?: "Неизвестная ошибка"
                )
            }
        }
    }
}

