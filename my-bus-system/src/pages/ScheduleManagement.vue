<template>
  <div class="route-management">
    <!-- 頁面標題 -->
    <div class="page-header">
      <div class="header-left">
        <h1 class="page-title">排班調度管理</h1>
        <p class="page-description">管理公車排班與調度安排</p>
      </div>
      <div class="header-right">
        <button
          @click="openCreateModal"
          class="btn-create"
          :disabled="!canWrite"
        >
          新增排班
        </button>
        <button
          @click="openBatchCreateModal"
          class="btn-batch"
          :disabled="!canWrite"
        >
          批次新增
        </button>
      </div>
    </div>

    <!-- 篩選區塊 -->
    <div class="filters-section">
      <!-- 搜尋欄 -->
      <div class="search-row">
        <div class="search-container">
          <div class="search-input-wrapper">
            <span class="search-icon">🔍</span>
            <input 
              v-model="keyword" 
              @input="debouncedSearch" 
              type="text" 
              placeholder="搜尋路線、車牌、駕駛員..." 
              class="search-input" 
            />
          </div>
        </div>
      </div>

      <!-- 篩選條件行 -->
      <div class="filter-controls-row">
        <div class="filter-group">
          <label class="filter-label">路線：</label>
          <select v-model="filters.route_no" @change="refresh" class="page-size-select">
            <option value="">全部路線</option>
            <option v-for="route in availableRoutes" :key="route.route_id" :value="route.route_id">
              {{ route.route_id }} - {{ route.route_name }}
            </option>
          </select>
        </div>

        <div class="filter-group">
          <label class="filter-label">營運狀態：</label>
          <select v-model="filters.operation_status" @change="refresh" class="page-size-select">
            <option value="">全部</option>
            <option value="正常營運">正常營運</option>
            <option value="暫停營運">暫停營運</option>
            <option value="維修中">維修中</option>
          </select>
        </div>

        <div class="filter-group-time">
          <label class="filter-label">日期範圍：</label>
          <div class="range-container">
            <input 
              v-model="filters.date_from" 
              @change="refresh" 
              type="date" 
              class="page-size-select date-input"
            />
            <span class="range-separator">至</span>
            <input 
              v-model="filters.date_to" 
              @change="refresh" 
              type="date" 
              class="page-size-select date-input"
            />
          </div>
        </div>

        <div class="filter-group-time">
          <label class="filter-label">時間範圍：</label>
          <div class="range-container">
            <input 
              v-model="filters.time_from" 
              @change="refresh" 
              type="time" 
              class="page-size-select time-input"
            />
            <span class="range-separator">至</span>
            <input 
              v-model="filters.time_to" 
              @change="refresh" 
              type="time" 
              class="page-size-select time-input"
            />
          </div>
        </div>
      </div>

      <!-- 排序和分頁設定行 -->
      <div class="filter-bottom-row">
        <div class="filter-group">
          <label class="filter-label">排序：</label>
          <select v-model="sortOrder" @change="refresh" class="page-size-select">
            <option value="route_asc">路線+方向+時間</option>
            <option value="departure_asc">發車時間由早到晚</option>
            <option value="departure_desc">發車時間由晚到早</option>
            <option value="date_asc">日期由新到舊</option>
            <option value="date_desc">日期由舊到新</option>
            <option value="route_desc">路線編號由大到小</option>
          </select>
        </div>

        <div class="filter-group">
          <label class="filter-label">每頁：</label>
          <select v-model="pageSize" @change="refresh" class="page-size-select">
            <option value="10">10</option>
            <option value="20">20</option>
            <option value="50">50</option>
          </select>
        </div>

        <div class="filter-group">
          <label class="filter-label">&nbsp;</label>
          <button @click="clearFilters" class="btn-clear-filters" title="清除篩選">
            清除篩選
          </button>
        </div>
      </div>
    </div>

    <!-- 主要表格 -->
    <div class="table-container">
      <table class="admin-table">
        <thead>
          <tr>
            <th>路線名稱</th>
            <th>往/返/其他</th>
            <th>營運型態</th>
            <th>營運狀態</th>
            <th>日期</th>
            <th>發車時間</th>
            <th>牌照號碼</th>
            <th>車輛狀態</th>
            <th>駕駛員</th>
            <th>員工編號</th>
            <th class="actions-column">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="schedule in schedules" :key="schedule.id" class="table-row">
            <td>{{ schedule.route_name || '-' }}</td>
            <td>
              <span class="direction-badge">{{ schedule.direction || '-' }}</span>
            </td>
            <td>{{ schedule.special_type || '-' }}</td>
            <td>
              <span :class="['status-badge', getOperationStatusClass(schedule.operation_status)]">
                {{ schedule.operation_status || '-' }}
              </span>
            </td>
            <td>{{ schedule.date || '-' }}</td>
            <td>{{ formatTime(schedule.departure_time) }}</td>
            <td class="license-cell">
              <span class="license-plate">{{ schedule.license_plate }}</span>
            </td>
            <td>
              <span :class="['status-badge', getCarStatusClass(schedule.car_status)]">
                {{ schedule.car_status || '-' }}
              </span>
            </td>
            <td>{{ schedule.driver_name }}</td>
            <td>{{ schedule.employee_id }}</td>
            <td class="actions-cell">
              <div class="action-buttons">
                <button @click="openEditModal(schedule)" class="btn-edit" :disabled="!canWrite" title="編輯">✏️</button>
                <button @click="askDelete(schedule)" class="btn-delete" :disabled="!canWrite" title="刪除">🗑️</button>
              </div>
            </td>
          </tr>
        </tbody>
      </table>

      <!-- 空狀態 -->
      <div v-if="!loading && schedules.length === 0" class="empty-state">
        <div class="empty-icon">📅</div>
        <h3>暫無排班資料</h3>
        <p>目前沒有找到符合條件的排班記錄</p>
      </div>

      <!-- 載入狀態 -->
      <div v-if="loading" class="loading-state">
        <div class="loading-spinner"></div>
        <p>載入中...</p>
      </div>
    </div>

    <!-- 分頁 -->
    <div v-if="pagination.total > 0" class="pagination-container">
      <div class="pagination-info">
        顯示第 {{ (pagination.page - 1) * pagination.limit + 1 }} 到 
        {{ Math.min(pagination.page * pagination.limit, pagination.total) }} 筆，
        共 {{ pagination.total }} 筆
      </div>
      <div class="pagination-controls">
        <button 
          @click="changePage(pagination.page - 1)" 
          :disabled="pagination.page <= 1"
          class="pagination-btn"
        >
          上一頁
        </button>
        <span class="pagination-numbers">
          <button 
            v-for="page in getPageNumbers()" 
            :key="page"
            @click="changePage(page)"
            :class="['pagination-number', { active: page === pagination.page }]"
          >
            {{ page }}
          </button>
        </span>
        <button 
          @click="changePage(pagination.page + 1)" 
          :disabled="pagination.page >= pagination.pages"
          class="pagination-btn"
        >
          下一頁
        </button>
      </div>
    </div>

    <!-- 新增/編輯模態框 -->
    <div v-if="showModal" class="modal-overlay" @click="closeModal">
      <div class="modal-content" @click.stop>
        <div class="modal-header">
          <h2>{{ editMode ? '編輯排班' : '新增排班' }}</h2>
          <button @click="closeModal" class="close-btn">×</button>
        </div>

        <form @submit.prevent="save" class="modal-form">
          <div class="form-content">
            <!-- 第一行：路線和方向 -->
            <div class="form-row">
              <div class="form-group">
                <label class="form-label">路線編號 <span class="required">*</span></label>
                <select 
                  v-model="form.route_no" 
                  class="form-select"
                  required
                >
                  <option value="">請選擇路線</option>
                  <option v-for="route in availableRoutes" :key="route.route_id" :value="route.route_id">
                    {{ route.route_id }} - {{ route.route_name }}
                  </option>
                </select>
              </div>
              <div class="form-group">
                <label class="form-label">往/返/其他 <span class="required" v-if="form.operation_status === '正常營運'">*</span></label>
                <select 
                  v-model="form.direction" 
                  class="form-select"
                  :required="form.operation_status === '正常營運'"
                >
                  <option value="">請選擇</option>
                  <option value="去程">去程</option>
                  <option value="返程">返程</option>
                  <option value="其他">其他</option>
                </select>
              </div>
            </div>

            <!-- 第二行：營運型態和營運狀態 -->
            <div class="form-row">
              <div class="form-group">
                <label class="form-label">營運型態 <span class="required" v-if="form.operation_status === '正常營運' && form.route_no && isExcelRoute(Number(form.route_no))">*</span></label>
                <select 
                  v-if="form.route_no && isExcelRoute(Number(form.route_no))"
                  v-model="form.special_type" 
                  class="form-select"
                  :required="form.operation_status === '正常營運'"
                >
                  <option value="">請選擇</option>
                  <option value="平日">平日</option>
                  <option value="假日">假日</option>
                  <option value="寒暑假">寒暑假</option>
                </select>
                <input 
                  v-else
                  v-model="form.special_type" 
                  type="text" 
                  class="form-input" 
                  placeholder="如：假日班次、夜間專車等"
                />
              </div>
              <div class="form-group">
                <label class="form-label">營運狀態</label>
                <select v-model="form.operation_status" class="form-select">
                  <option value="">請選擇</option>
                  <option value="正常營運">正常營運</option>
                  <option value="暫停營運">暫停營運</option>
                  <option value="維修中">維修中</option>
                </select>
              </div>
            </div>

            <!-- 第三行：日期和發車時間 -->
            <div class="form-row">
              <div class="form-group">
                <label class="form-label">日期 <span class="required" v-if="form.operation_status === '正常營運'">*</span></label>
                <input v-model="form.date" type="date" class="form-input" :required="form.operation_status === '正常營運'">
              </div>
              <div class="form-group">
                <label class="form-label">發車時間(Excel) <span class="required" v-if="form.operation_status === '正常營運' && !form.departure_time_manual">*</span></label>
                
                <!-- Excel路線使用下拉選單 -->
                <select 
                  v-if="form.route_no && isExcelRoute(Number(form.route_no))"
                  v-model="form.departure_time" 
                  class="form-select" 
                  :required="form.operation_status === '正常營運' && !form.departure_time_manual"
                  :disabled="!form.route_no || !form.special_type || (Number(form.route_no) !== 3 && !form.direction) || !!form.departure_time_manual"
                >
                  <option value="">
                    {{ form.departure_time_manual ? '已選擇手動輸入' :
                       !form.route_no ? '請先選擇路線' :
                       !form.special_type ? '請先選擇營運型態' :
                       (Number(form.route_no) !== 3 && !form.direction) ? '請先選擇方向' : 
                       availableDepartureTimes.length === 0 ? '載入中...' : '請選擇發車時間' }}
                  </option>
                  <option v-for="time in availableDepartureTimes" :key="time" :value="time">
                    {{ time }}
                  </option>
                </select>
                
                <!-- 非Excel路線顯示提示 -->
                <input 
                  v-else
                  type="text" 
                  class="form-input" 
                  value="此路線無Excel資料，請使用手動輸入"
                  disabled
                  style="background: #f8f9fa; color: #6c757d;"
                />
              </div>
              <div class="form-group">
                <label class="form-label">發車時間(手動) <span class="required" v-if="form.operation_status === '正常營運' && !form.departure_time">*</span></label>
                <input 
                  v-model="form.departure_time_manual" 
                  type="time" 
                  class="form-input" 
                  :required="form.operation_status === '正常營運' && !form.departure_time"
                  :disabled="!form.route_no || !!form.departure_time"
                  :placeholder="form.departure_time ? '已選擇Excel時間' : '請輸入發車時間'"
                />
              </div>
            </div>

            <!-- 第四行：牌照號碼 -->
            <div class="form-row">
              <div class="form-group">
                <label class="form-label">牌照號碼 <span class="required" v-if="form.operation_status === '正常營運'">*</span></label>
                <select v-model="form.license_plate" class="form-select" :required="form.operation_status === '正常營運'">
                  <option value="">請選擇車輛</option>
                  <option v-for="car in availableCars" :key="car.car_licence" :value="car.car_licence">
                    {{ car.car_licence }} ({{ car.car_status }})
                  </option>
                </select>
              </div>
            </div>

            <!-- 第五行：駕駛員資訊 -->
            <div class="form-row">
              <div class="form-group">
                <label class="form-label">駕駛員選擇(Excel) <span class="required" v-if="form.operation_status === '正常營運' && selectedDriverId === '' && !form.driver_name && !form.employee_id">*</span></label>
                <select 
                  v-model="selectedDriverId" 
                  @change="onDriverSelect" 
                  class="form-select" 
                  :required="form.operation_status === '正常營運' && selectedDriverId === '' && !form.driver_name && !form.employee_id"
                  :disabled="selectedDriverId === '' && !!(form.driver_name || form.employee_id)"
                >
                  <option value="">{{ (selectedDriverId === '' && (form.driver_name || form.employee_id)) ? '已選擇手動輸入' : '請選擇駕駛員' }}</option>
                  <option v-for="(driver, index) in availableDrivers" :key="`${driver.driver_name}-${driver.employee_number}`" :value="index">
                    {{ driver.driver_name }} ({{ driver.employee_number }})
                  </option>
                </select>
              </div>
            </div>
            
            <!-- 第六行：手動輸入駕駛員資訊 -->
            <div class="form-row">
              <div class="form-group">
                <label class="form-label">駕駛員姓名(手動) <span class="required" v-if="form.operation_status === '正常營運' && selectedDriverId === '' && !form.employee_id">*</span></label>
                <input 
                  v-model="form.driver_name" 
                  type="text" 
                  class="form-input" 
                  placeholder="請輸入駕駛員姓名" 
                  :required="form.operation_status === '正常營運' && selectedDriverId === '' && !form.employee_id"
                  :disabled="selectedDriverId !== ''"
                />
              </div>
              <div class="form-group">
                <label class="form-label">員工編號(手動) <span class="required" v-if="form.operation_status === '正常營運' && selectedDriverId === '' && !form.driver_name">*</span></label>
                <input 
                  v-model="form.employee_id" 
                  type="text" 
                  class="form-input" 
                  placeholder="請輸入員工編號" 
                  :required="form.operation_status === '正常營運' && selectedDriverId === '' && !form.driver_name"
                  :disabled="selectedDriverId !== ''"
                />
              </div>
            </div>
          </div>

          <div class="form-actions">
            <button type="button" class="btn-secondary" @click="closeModal">取消</button>
            <button type="submit" class="btn-primary" :disabled="saving">
              {{ saving ? '儲存中...' : (editMode ? '更新' : '新增') }}
            </button>
          </div>
        </form>
      </div>
    </div>

    <!-- 刪除確認模態框 -->
    <div v-if="showDeleteModal" class="modal-overlay" @click="cancelDelete">
      <div class="modal-content delete-modal" @click.stop>
        <div class="modal-header">
          <h2>確認刪除</h2>
          <button class="close-btn" @click="cancelDelete">×</button>
        </div>
        <div class="modal-body">
          <p>確定要刪除排班「{{ toDelete?.route_name }}」嗎？</p>
          <div class="delete-info">
            <p><strong>路線：</strong>{{ toDelete?.route_name }}</p>
            <p><strong>方向：</strong>{{ toDelete?.direction }}</p>
            <p><strong>日期：</strong>{{ toDelete?.date }}</p>
            <p><strong>時間：</strong>{{ formatTime(toDelete?.departure_time || '') }}</p>
            <p><strong>車牌：</strong>{{ toDelete?.license_plate }}</p>
          </div>
          <p class="warning-text">此操作無法復原。</p>
        </div>
        <div class="form-actions">
          <button class="btn-secondary" @click="cancelDelete">取消</button>
          <button class="btn-danger" @click="confirmDelete" :disabled="deleting">
            {{ deleting ? '刪除中...' : '確認刪除' }}
          </button>
        </div>
      </div>
    </div>

    <!-- 批次新增模態框 -->
    <div v-if="showBatchModal" class="modal-overlay" @click="closeBatchModal">
      <div class="modal-content batch-modal" @click.stop>
        <div class="modal-header">
          <h2>批次新增排班</h2>
          <button class="close-btn" @click="closeBatchModal">×</button>
        </div>

        <div class="modal-body">
          <!-- 檔案上傳區 -->
          <div class="upload-section">
            <div 
              class="upload-area" 
              :class="{ 'drag-over': isDragging }"
              @drop.prevent="handleDrop"
              @dragover.prevent="isDragging = true"
              @dragleave.prevent="isDragging = false"
              @click="triggerFileInput"
            >
              <input 
                ref="fileInput" 
                type="file" 
                accept=".xlsx,.xls" 
                @change="handleFileSelect"
                style="display: none"
              >
              <div class="upload-icon">📥</div>
              <p class="upload-text">拖拽或點擊上傳 Excel 檔案</p>
              <p class="upload-hint">支援 .xlsx 或 .xls 格式</p>
            </div>
            <div class="upload-actions">
              <button class="btn-download-template" @click="downloadTemplate">
                📄 下載範本
              </button>
            </div>
          </div>

          <!-- 檔案資訊 -->
          <div v-if="batchFile" class="file-info">
            <span class="file-name">📎 {{ batchFile.name }}</span>
            <span class="file-size">({{ formatFileSize(batchFile.size) }})</span>
            <button class="btn-remove-file" @click="removeBatchFile">✕</button>
          </div>

          <!-- 資料預覽 -->
          <div v-if="batchData.length > 0" class="preview-section">
            <h3>📊 預覽資料（{{ batchData.length }} 筆）</h3>
            <div class="preview-table-container">
              <table class="preview-table">
                <thead>
                  <tr>
                    <th>#</th>
                    <th>路線</th>
                    <th>方向</th>
                    <th>營運型態</th>
                    <th>日期</th>
                    <th>時間</th>
                    <th>車牌</th>
                    <th>駕駛員</th>
                    <th>員工編號</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="(item, index) in batchData" :key="index" :class="{ 'error-row': item.hasError }">
                    <td>{{ index + 1 }}</td>
                    <td>{{ item.route_no }}</td>
                    <td>{{ item.direction }}</td>
                    <td>{{ item.special_type }}</td>
                    <td>{{ item.date }}</td>
                    <td>{{ item.departure_time }}</td>
                    <td>{{ item.license_plate }}</td>
                    <td>{{ item.driver_name }}</td>
                    <td>{{ item.employee_id }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>

          <!-- 驗證狀態 -->
          <div v-if="batchData.length > 0" class="validation-section">
            <div v-if="batchValidating" class="validation-loading">
              <div class="loading-spinner"></div>
              <p>驗證中...</p>
            </div>

            <div v-else-if="batchValidationResult">
              <!-- 驗證通過 -->
              <div v-if="batchValidationResult.all_valid" class="validation-success">
                <h3>✅ 驗證通過</h3>
                <p>所有資料驗證成功，可以匯入</p>
              </div>

              <!-- 驗證失敗 -->
              <div v-else class="validation-error">
                <h3>❌ 發現 {{ batchValidationResult.errors.length }} 個錯誤，無法匯入</h3>
                <div class="error-list">
                  <div v-for="(error, index) in batchValidationResult.errors" :key="index" class="error-item">
                    <strong>第 {{ error.row }} 行：</strong>
                    <span>{{ error.message }}</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>

        <div class="form-actions">
          <button class="btn-secondary" @click="closeBatchModal">取消</button>
          <button 
            class="btn-primary" 
            @click="confirmBatchCreate"
            :disabled="!canConfirmBatch"
          >
            {{ batchCreating ? '匯入中...' : '確認匯入' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed, watch } from 'vue'
import * as XLSX from 'xlsx'

// 類型定義
interface Schedule {
  id: number
  route_no: string
  route_name?: string
  direction?: string
  special_type?: string
  operation_status?: string
  date: string
  departure_time: string
  license_plate: string
  car_status?: string
  driver_name: string
  employee_id: string
}

interface Route {
  route_id: string
  route_name: string
}

interface Car {
  car_licence: string
  car_status: string
}

interface Driver {
  driver_name: string
  employee_number: string
}

// 響應式數據
const schedules = ref<Schedule[]>([])
const availableRoutes = ref<Route[]>([])
const availableCars = ref<Car[]>([])
const availableDrivers = ref<Driver[]>([])
const availableDepartureTimes = ref<string[]>([])
const loading = ref(false)
const showModal = ref(false)
const editMode = ref(false)
const saving = ref(false)
const showDeleteModal = ref(false)
const deleting = ref(false)
const toDelete = ref<Schedule | null>(null)

// 分頁
const pagination = ref({
  page: 1,
  limit: 20,
  total: 0,
  pages: 0
})

// 取得今天的日期字串 (YYYY-MM-DD)
const getTodayDateString = () => {
  const today = new Date()
  const year = today.getFullYear()
  const month = String(today.getMonth() + 1).padStart(2, '0')
  const day = String(today.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

// 篩選條件
const keyword = ref('')
const pageSize = ref(50)
const sortOrder = ref('route_asc') // 預設依路線編號排序
const filters = ref({
  route_no: '',
  operation_status: '正常營運', // 預設顯示正常營運
  date_from: getTodayDateString(), // 預設當日
  date_to: getTodayDateString(),   // 預設當日
  time_from: '',
  time_to: ''
})

// 表單數據
const form = ref({
  id: null as number | null,
  route_no: '',
  direction: '',
  special_type: '',
  operation_status: '',
  date: '',
  departure_time: '',
  departure_time_manual: '',
  license_plate: '',
  driver_name: '',
  employee_id: ''
})

// 駕駛員選擇相關
const selectedDriverId = ref('')

// 批次新增相關
const showBatchModal = ref(false)
const batchFile = ref<File | null>(null)
const batchData = ref<any[]>([])
const batchValidationResult = ref<any>(null)
const batchValidating = ref(false)
const batchCreating = ref(false)
const isDragging = ref(false)
const fileInput = ref<HTMLInputElement | null>(null)

// 計算屬性
const canWrite = computed(() => {
  // 檢查localStorage中是否有token，有的話就表示已登入
  const token = localStorage.getItem('token')
  return !!token
})

const canConfirmBatch = computed(() => {
  return batchValidationResult.value?.all_valid === true && !batchCreating.value
})

// 獲取認證token
const getAuthToken = () => {
  return localStorage.getItem('token') || 'admin_1_token'
}

// 格式化時間顯示（只顯示 HH:MM）
const formatTime = (timeString: string): string => {
  if (!timeString) return '-'
  
  // 如果時間字符串包含秒數，則截取前5位（HH:MM）
  if (timeString.includes(':')) {
    const parts = timeString.split(':')
    if (parts.length >= 2) {
      return `${parts[0].padStart(2, '0')}:${parts[1].padStart(2, '0')}`
    }
  }
  
  return timeString
}

// 檢查路線是否需要從Excel讀取發車時間
const isExcelRoute = (routeId: number): boolean => {
  // 只有路線1、2、3從Excel讀取，其他路線（包括路線4-行動遊花蓮、路線18等）都自由輸入
  return [1, 2, 3].includes(routeId)
}

// 根據營運型態、路線ID和方向取得Excel工作表名稱
const getRouteExcelName = (specialType: string, routeId: number, direction: string): string => {
  console.log('Getting Excel name for:', { specialType, routeId, direction })
  
  // 檢查是否為Excel路線
  if (!isExcelRoute(routeId)) {
    console.log('Route', routeId, 'is not an Excel route, returning empty')
    return ''
  }
  
  // 如果沒有營運型態，無法生成完整的工作表名稱
  if (!specialType) {
    console.log('No special type specified')
    return ''
  }
  
  // 將路線ID映射到Excel工作表名稱
  const routeMapping: Record<number, string> = {
    1: '市民小巴5',
    2: '市民小巴6', 
    3: '市民小巴7'
  }
  
  const baseName = routeMapping[routeId] || `未知路線${routeId}`
  console.log('Base name:', baseName)
  
  // 市民小巴7只有一個工作表，不分去程回程
  if (baseName === '市民小巴7') {
    const result = `${specialType}-${baseName}`
    console.log('Route 7 detected, returning:', result)
    return result
  }
  
  // 其他路線需要加上方向
  if (direction === '去程') {
    const result = `${specialType}-${baseName}(去程)`
    console.log('Go direction, returning:', result)
    return result
  } else if (direction === '返程') {
    const result = `${specialType}-${baseName}(回程)`  // Excel中是"回程"不是"返程"
    console.log('Return direction, returning:', result)
    return result
  }
  
  console.log('No direction specified, returning empty string')
  return ''
}

// 監聽營運狀態變化，自動清空相關欄位
watch(() => form.value.operation_status, (newStatus) => {
  if (newStatus !== '正常營運') {
    // 暫停營運或維修中時清空日期、發車時間、車牌和駕駛員資料
    form.value.date = ''
    form.value.departure_time = ''
    form.value.departure_time_manual = ''
    form.value.license_plate = ''
    form.value.driver_name = ''
    form.value.employee_id = ''
    selectedDriverId.value = ''
  }
})

// 監聽路線變化，載入對應的發車時間
watch(() => form.value.route_no, async (newRouteNo) => {
  // 清空發車時間和方向
  form.value.departure_time = ''
  form.value.departure_time_manual = ''
  form.value.direction = ''
  
  if (newRouteNo) {
    const routeId = Number(newRouteNo)
    
    // 檢查是否為Excel路線
    if (isExcelRoute(routeId)) {
      if (routeId === 1 || routeId === 2) {
        // 市民小巴5和6需要選擇方向，預設為去程
        form.value.direction = '去程'
      } else if (routeId === 3) {
        // 市民小巴7不分方向
        form.value.direction = ''
      }
      
      // 只有當營運型態也選擇了才載入發車時間
      if (form.value.special_type) {
        const routeName = getRouteExcelName(form.value.special_type, routeId, form.value.direction)
        console.log('Route watch - specialType:', form.value.special_type, 'routeId:', routeId, 'direction:', form.value.direction, 'routeName:', routeName)
        
        if (routeName) {
          await fetchDepartureTimes(routeName)
        }
      } else {
        // 如果沒有營運型態，清空發車時間選項
        availableDepartureTimes.value = []
      }
    } else {
      // 非Excel路線，清空發車時間選項，允許自由輸入
      console.log('Non-Excel route detected, allowing free input')
      availableDepartureTimes.value = []
    }
  } else {
    availableDepartureTimes.value = []
  }
})

// 監聽方向變化，重新載入發車時間
watch(() => form.value.direction, async (newDirection) => {
  // 清空發車時間
  form.value.departure_time = ''
  form.value.departure_time_manual = ''
  
  if (form.value.route_no && newDirection) {
    const routeId = Number(form.value.route_no)
    
    // 只有Excel路線才需要重新載入發車時間
    if (isExcelRoute(routeId) && form.value.special_type) {
      const routeName = getRouteExcelName(form.value.special_type, routeId, newDirection)
      if (routeName) {
        await fetchDepartureTimes(routeName)
      }
    }
  } else {
    // 如果不是Excel路線，保持空的發車時間選項
    if (!form.value.route_no || !isExcelRoute(Number(form.value.route_no))) {
      availableDepartureTimes.value = []
    }
  }
})

// 監聽營運型態變化，重新載入發車時間
watch(() => form.value.special_type, async (newSpecialType) => {
  // 清空發車時間
  form.value.departure_time = ''
  form.value.departure_time_manual = ''
  
  if (form.value.route_no && newSpecialType) {
    const routeId = Number(form.value.route_no)
    
    // 只有Excel路線才需要重新載入發車時間
    if (isExcelRoute(routeId)) {
      // 確保市民小巴7有方向或其他路線已選擇方向
      if (routeId === 3 || form.value.direction) {
        const routeName = getRouteExcelName(newSpecialType, routeId, form.value.direction)
        console.log('Special type watch - specialType:', newSpecialType, 'routeId:', routeId, 'direction:', form.value.direction, 'routeName:', routeName)
        
        if (routeName) {
          await fetchDepartureTimes(routeName)
        }
      }
    }
  } else if (!newSpecialType) {
    // 清空營運型態時，清空發車時間選項
    availableDepartureTimes.value = []
  }
})

// 監聽 departure_time 變化，自動清空 departure_time_manual
watch(() => form.value.departure_time, (newVal) => {
  if (newVal) {
    form.value.departure_time_manual = ''
  }
})

// 監聽 departure_time_manual 變化，自動清空 departure_time
watch(() => form.value.departure_time_manual, (newVal) => {
  if (newVal) {
    form.value.departure_time = ''
  }
})

// 監聽 Excel 選擇時間變化，清空手動輸入
watch(() => form.value.departure_time, (newValue) => {
  if (newValue) {
    form.value.departure_time_manual = ''
  }
})

// 監聽手動輸入時間變化，清空 Excel 選擇
watch(() => form.value.departure_time_manual, (newValue) => {
  if (newValue) {
    form.value.departure_time = ''
  }
})

// 監聽 Excel 選擇時間變化，清空手動輸入
watch(() => form.value.departure_time, (newValue) => {
  if (newValue) {
    form.value.departure_time_manual = ''
  }
})

// 監聽手動輸入時間變化，清空 Excel 選擇
watch(() => form.value.departure_time_manual, (newValue) => {
  if (newValue) {
    form.value.departure_time = ''
  }
})

// 防抖搜尋
let searchTimeout: number | null = null
const debouncedSearch = () => {
  if (searchTimeout) clearTimeout(searchTimeout)
  searchTimeout = setTimeout(() => {
    pagination.value.page = 1
    fetchSchedules()
  }, 500)
}

// 取得營運狀態樣式類別
const getOperationStatusClass = (status: string | undefined) => {
  switch (status) {
    case '正常營運': return 'status-active'
    case '暫停營運': return 'status-warning'
    case '維修中': return 'status-danger'
    default: return 'status-secondary'
  }
}

// 取得車輛狀態樣式類別
const getCarStatusClass = (status: string | undefined) => {
  switch (status) {
    case 'service': return 'status-active'
    case 'paused': return 'status-warning'
    case 'maintenance': return 'status-danger'
    case 'retired': return 'status-secondary'
    default: return 'status-secondary'
  }
}

// API 調用函數
const fetchSchedules = async () => {
  loading.value = true
  try {
    const params = new URLSearchParams({
      page: pagination.value.page.toString(),
      limit: pageSize.value.toString()
    })
    
    if (keyword.value.trim()) params.append('search', keyword.value.trim())
    if (filters.value.route_no) params.append('route_no', filters.value.route_no)
    if (filters.value.operation_status) params.append('operation_status', filters.value.operation_status)
    if (filters.value.date_from) params.append('date_from', filters.value.date_from)
    if (filters.value.date_to) params.append('date_to', filters.value.date_to)
    if (filters.value.time_from) params.append('time_from', filters.value.time_from)
    if (filters.value.time_to) params.append('time_to', filters.value.time_to)
    if (sortOrder.value) params.append('sort', sortOrder.value)

    const response = await fetch(`/api/schedules?${params}`, {
      headers: { 'Authorization': `Bearer ${getAuthToken()}` }
    })
    
    if (!response.ok) throw new Error('Failed to fetch schedules')
    
    const data = await response.json()
    schedules.value = data.data
    pagination.value = data.pagination
  } catch (error) {
    console.error('Error fetching schedules:', error)
    alert('載入排班資料失敗')
  } finally {
    loading.value = false
  }
}

const fetchRoutes = async () => {
  try {
    const response = await fetch('/api/schedules/routes', {
      headers: { 'Authorization': `Bearer ${getAuthToken()}` }
    })
    if (response.ok) {
      const data = await response.json()
      availableRoutes.value = data.data
    }
  } catch (error) {
    console.error('Error fetching routes:', error)
  }
}

const fetchCars = async () => {
  try {
    const response = await fetch('/api/schedules/cars', {
      headers: { 'Authorization': `Bearer ${getAuthToken()}` }
    })
    if (response.ok) {
      const data = await response.json()
      availableCars.value = data.data
    }
  } catch (error) {
    console.error('Error fetching cars:', error)
  }
}

const fetchDrivers = async () => {
  try {
    const response = await fetch('/api/schedules/drivers', {
      headers: { 'Authorization': `Bearer ${getAuthToken()}` }
    })
    if (response.ok) {
      const data = await response.json()
      availableDrivers.value = data.data
    }
  } catch (error) {
    console.error('Error fetching drivers:', error)
  }
}

const fetchDepartureTimes = async (routeName: string) => {
  try {
    console.log('Fetching departure times for route:', routeName)
    
    if (!routeName) {
      availableDepartureTimes.value = []
      return
    }

    const response = await fetch(`/api/schedules/departure-times/${encodeURIComponent(routeName)}`, {
      headers: { 'Authorization': `Bearer ${getAuthToken()}` }
    })
    
    console.log('Response status:', response.status)
    
    if (response.ok) {
      const data = await response.json()
      console.log('Response data:', data)
      
      if (data.success) {
        availableDepartureTimes.value = data.data
        console.log('Available departure times:', data.data)
      } else {
        console.error('Failed to fetch departure times:', data.error)
        availableDepartureTimes.value = []
      }
    } else {
      console.error('Failed to fetch departure times:', response.statusText)
      availableDepartureTimes.value = []
    }
  } catch (error) {
    console.error('Error fetching departure times:', error)
    availableDepartureTimes.value = []
  }
}

// 模態框操作
const openCreateModal = () => {
  if (!canWrite.value) return
  editMode.value = false
  resetForm()
  showModal.value = true
}

const openEditModal = async (schedule: Schedule) => {
  if (!canWrite.value) return
  editMode.value = true
  form.value = {
    id: schedule.id,
    route_no: schedule.route_no,
    direction: schedule.direction || '',
    special_type: schedule.special_type || '',
    operation_status: schedule.operation_status || '',
    date: schedule.date,
    departure_time: schedule.departure_time,
    departure_time_manual: '',
    license_plate: schedule.license_plate,
    driver_name: schedule.driver_name,
    employee_id: schedule.employee_id
  }
  
  // 載入對應路線的發車時間（只有Excel路線才需要）
  if (schedule.route_no) {
    const routeId = Number(schedule.route_no)
    const direction = schedule.direction || ''
    
    console.log('Edit modal - routeId:', routeId, 'direction:', direction)
    
    if (isExcelRoute(routeId)) {
      const routeName = getRouteExcelName(schedule.special_type || '', routeId, direction)
      console.log('Excel route detected, routeName:', routeName)
      
      if (routeName) {
        await fetchDepartureTimes(routeName)
      }
    } else {
      console.log('Non-Excel route, allowing free input')
      availableDepartureTimes.value = []
    }
  }
  
  // 嘗試找到對應的駕駛員並設定選擇狀態
  selectedDriverId.value = ''
  if (schedule.driver_name && schedule.employee_id) {
    const driverIndex = availableDrivers.value.findIndex(driver => 
      driver.driver_name === schedule.driver_name && driver.employee_number === schedule.employee_id
    )
    if (driverIndex !== -1) {
      selectedDriverId.value = driverIndex.toString()
    }
  }
  
  showModal.value = true
}

const closeModal = () => {
  showModal.value = false
  resetForm()
}

const resetForm = () => {
  form.value = {
    id: null,
    route_no: '',
    direction: '',
    special_type: '',
    operation_status: '',
    date: '',
    departure_time: '',
    departure_time_manual: '',
    license_plate: '',
    driver_name: '',
    employee_id: ''
  }
  selectedDriverId.value = ''
}

// 駕駛員選擇處理
const onDriverSelect = () => {
  if (selectedDriverId.value !== '' && availableDrivers.value.length > 0) {
    const driverIndex = parseInt(selectedDriverId.value)
    const selectedDriver = availableDrivers.value[driverIndex]
    if (selectedDriver) {
      // 填入駕駛員資料，手動輸入欄位會自動禁用
      form.value.driver_name = selectedDriver.driver_name
      form.value.employee_id = selectedDriver.employee_number
    }
  } else {
    // 選擇「請選擇駕駛員」時，清空表單中的駕駛員資料
    form.value.driver_name = ''
    form.value.employee_id = ''
  }
}

// 檢查衝突
const checkConflicts = () => {
  const conflicts = []
  
  // 移除路線重複檢查，允許同一路線在不同時間多次排班
  
  // 只有正常營運才檢查車牌和駕駛員衝突
  if (form.value.operation_status === '正常營運') {
    // 檢查相同車牌、日期、時間的衝突（同一時間同一車牌不能重複使用）
    const carConflict = schedules.value.find(s =>
      s.id !== form.value.id &&
      s.license_plate === form.value.license_plate &&
      s.date === form.value.date &&
      s.departure_time === form.value.departure_time
    )
    
    if (carConflict) {
      conflicts.push(`車牌 ${form.value.license_plate} 在 ${form.value.date} ${form.value.departure_time} 時段已有排班`)
    }
    
    // 檢查相同駕駛員、日期、時間的衝突（同一時間同一駕駛員不能重複排班）
    const driverConflict = schedules.value.find(s =>
      s.id !== form.value.id &&
      s.driver_name === form.value.driver_name &&
      s.date === form.value.date &&
      s.departure_time === form.value.departure_time
    )
    
    if (driverConflict) {
      conflicts.push(`駕駛員 ${form.value.driver_name} 在 ${form.value.date} ${form.value.departure_time} 時段已有排班`)
    }
    
    // 檢查相同員工編號、日期、時間的衝突（同一時間同一員工編號不能重複排班）
    const employeeConflict = schedules.value.find(s =>
      s.id !== form.value.id &&
      s.employee_id === form.value.employee_id &&
      s.date === form.value.date &&
      s.departure_time === form.value.departure_time
    )
    
    if (employeeConflict) {
      conflicts.push(`員工編號 ${form.value.employee_id} 在 ${form.value.date} ${form.value.departure_time} 時段已有排班`)
    }
  }
  
  return conflicts
}

// 儲存操作
const save = async () => {
  if (!canWrite.value) return
  
  // 檢查衝突（新增和編輯模式都需要檢查）
  const conflicts = checkConflicts()
  if (conflicts.length > 0) {
    alert('發現衝突：\n' + conflicts.join('\n'))
    return
  }
  
  saving.value = true
  
  try {
    const method = editMode.value ? 'PUT' : 'POST'
    const url = editMode.value ? `/api/schedules/${form.value.id}` : '/api/schedules'
    
    // 建立 payload，根據營運狀態決定欄位
    const isNormalOperation = form.value.operation_status === '正常營運'
    
    // 建立基本 payload
    const basePayload: any = {}
    
    if (editMode.value) {
      // 編輯模式下：現在允許修改所有欄位
      if (form.value.route_no) basePayload.route_no = String(form.value.route_no)
      basePayload.direction = form.value.direction
      basePayload.special_type = form.value.special_type
      basePayload.operation_status = form.value.operation_status
    } else {
      // 新增模式下：基本欄位都需要
      basePayload.route_no = String(form.value.route_no)  // 確保是字符串類型
      basePayload.direction = form.value.direction
      basePayload.special_type = form.value.special_type
      basePayload.operation_status = form.value.operation_status
    }
    
    // 日期欄位：所有營運狀態都可以填寫日期
    if (form.value.date) basePayload.schedule_date = form.value.date
    
    // 只有正常營運才需要發車時間、車牌和駕駛員資料
    if (isNormalOperation) {
      // 優先使用 Excel 選擇的時間，其次使用手動輸入的時間
      const finalDepartureTime = form.value.departure_time || form.value.departure_time_manual
      if (finalDepartureTime) basePayload.departure_time = finalDepartureTime
      if (form.value.license_plate) basePayload.license_plate = form.value.license_plate
      if (form.value.driver_name) basePayload.driver_name = form.value.driver_name
      if (form.value.employee_id) basePayload.employee_id = form.value.employee_id
    }
    
    const payload = basePayload
    
    const response = await fetch(url, {
      method,
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${getAuthToken()}`
      },
      body: JSON.stringify(payload)
    })
    
    if (!response.ok) {
      const error = await response.json()
      throw new Error(error.detail || '操作失敗')
    }
    
    alert(editMode.value ? '更新成功' : '新增成功')
    
    // 重新載入排班列表
    fetchSchedules()
    
    // 編輯模式：關閉模態框
    // 新增模式：保持模態框開啟，重置表單以便繼續新增
    if (editMode.value) {
      closeModal()
    } else {
      // 保留路線、方向、營運型態、營運狀態，清空其他欄位
      const keepRouteNo = form.value.route_no
      const keepDirection = form.value.direction
      const keepSpecialType = form.value.special_type
      const keepOperationStatus = form.value.operation_status
      
      resetForm()
      
      // 恢復保留的欄位
      form.value.route_no = keepRouteNo
      form.value.direction = keepDirection
      form.value.special_type = keepSpecialType
      form.value.operation_status = keepOperationStatus
      
      // 如果是Excel路線，重新載入發車時間
      if (keepRouteNo && isExcelRoute(Number(keepRouteNo))) {
        const routeName = getRouteExcelName(keepSpecialType, Number(keepRouteNo), keepDirection)
        if (routeName) {
          await fetchDepartureTimes(routeName)
        }
      }
    }
  } catch (error: any) {
    console.error('Error saving schedule:', error)
    alert(error.message || '操作失敗')
  } finally {
    saving.value = false
  }
}

// 刪除功能
const askDelete = (schedule: Schedule) => {
  if (!canWrite.value) return
  toDelete.value = schedule
  showDeleteModal.value = true
}

const cancelDelete = () => {
  showDeleteModal.value = false
  toDelete.value = null
}

const confirmDelete = async () => {
  if (!toDelete.value) return
  
  deleting.value = true
  try {
    const response = await fetch(`/api/schedules/${toDelete.value.id}`, {
      method: 'DELETE',
      headers: {
        'Authorization': `Bearer ${getAuthToken()}`
      }
    })
    
    if (!response.ok) {
      const error = await response.json()
      throw new Error(error.detail || '刪除失敗')
    }
    
    alert('刪除成功')
    showDeleteModal.value = false
    toDelete.value = null
    fetchSchedules()
  } catch (error: any) {
    console.error('Error deleting schedule:', error)
    alert(error.message || '刪除失敗')
  } finally {
    deleting.value = false
  }
}

// 批次新增相關函數
const openBatchCreateModal = () => {
  showBatchModal.value = true
  batchFile.value = null
  batchData.value = []
  batchValidationResult.value = null
  batchValidating.value = false
  batchCreating.value = false
  isDragging.value = false
}

const closeBatchModal = () => {
  showBatchModal.value = false
  batchFile.value = null
  batchData.value = []
  batchValidationResult.value = null
  batchValidating.value = false
  batchCreating.value = false
  isDragging.value = false
}

const triggerFileInput = () => {
  fileInput.value?.click()
}

const handleFileSelect = async (event: Event) => {
  const target = event.target as HTMLInputElement
  const file = target.files?.[0]
  if (file) {
    await processFile(file)
  }
}

const handleDrop = async (event: DragEvent) => {
  isDragging.value = false
  const file = event.dataTransfer?.files[0]
  if (file && (file.name.endsWith('.xlsx') || file.name.endsWith('.xls'))) {
    await processFile(file)
  } else {
    alert('請上傳 Excel 檔案（.xlsx 或 .xls）')
  }
}

const removeBatchFile = () => {
  batchFile.value = null
  batchData.value = []
  batchValidationResult.value = null
  if (fileInput.value) {
    fileInput.value.value = ''
  }
}

const formatFileSize = (bytes: number): string => {
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(2) + ' KB'
  return (bytes / (1024 * 1024)).toFixed(2) + ' MB'
}

const processFile = async (file: File) => {
  batchFile.value = file
  batchValidating.value = true
  batchValidationResult.value = null
  
  try {
    // 解析Excel檔案
    const data = await parseExcelFile(file)
    
    if (data.length === 0) {
      alert('Excel 檔案中沒有資料')
      removeBatchFile()
      return
    }
    
    if (data.length > 500) {
      alert('資料筆數超過限制（最多 500 筆）')
      removeBatchFile()
      return
    }
    
    batchData.value = data
    
    // 前端基本驗證
    const frontendErrors = validateFrontend(data)
    
    if (frontendErrors.length > 0) {
      batchValidationResult.value = {
        all_valid: false,
        errors: frontendErrors
      }
      batchValidating.value = false
      return
    }
    
    // 後端深度驗證
    await validateBackend(data)
    
  } catch (error: any) {
    console.error('處理檔案錯誤:', error)
    alert('處理檔案時發生錯誤: ' + error.message)
    removeBatchFile()
  }
}

const parseExcelFile = async (file: File): Promise<any[]> => {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    
    reader.onload = async (e) => {
      try {
        const data = new Uint8Array(e.target?.result as ArrayBuffer)
        const workbook = XLSX.read(data, { type: 'array' })
        
        // 讀取第一個工作表
        const sheetName = workbook.SheetNames[0]
        const worksheet = workbook.Sheets[sheetName]
        
        // 轉換為JSON
        const jsonData = XLSX.utils.sheet_to_json(worksheet, { 
          header: 1,
          defval: '' 
        }) as any[][]
        
        if (jsonData.length === 0) {
          resolve([])
          return
        }
        
        // 第一行是標題
        const headers = jsonData[0]
        const rows = jsonData.slice(1)
        
        // 檢查必要欄位
        const requiredHeaders = ['路線編號', '方向', '日期', '發車時間', '牌照號碼', '駕駛員姓名', '員工編號']
        const missingHeaders = requiredHeaders.filter(h => !headers.includes(h))
        
        if (missingHeaders.length > 0) {
          reject(new Error(`缺少必要欄位: ${missingHeaders.join(', ')}`))
          return
        }
        
        // 建立欄位索引對應
        const headerMap: Record<string, number> = {}
        headers.forEach((h: string, i: number) => {
          headerMap[h] = i
        })
        
        // 轉換資料
        const parsedData = rows
          .filter(row => row && row.some(cell => cell !== '' && cell !== null))
          .map((row, index) => ({
            row_number: index + 2, // Excel行號（標題是第1行）
            route_no: String(row[headerMap['路線編號']] || '').trim(),
            direction: String(row[headerMap['方向']] || '').trim(),
            special_type: String(row[headerMap['營運型態']] || '').trim(),
            date: String(row[headerMap['日期']] || '').trim(),
            departure_time: String(row[headerMap['發車時間']] || '').trim(),
            license_plate: String(row[headerMap['牌照號碼']] || '').trim(),
            driver_name: String(row[headerMap['駕駛員姓名']] || '').trim(),
            employee_id: String(row[headerMap['員工編號']] || '').trim(),
            operation_status: '正常營運' // 固定值
          }))
        
        resolve(parsedData)
      } catch (error) {
        reject(error)
      }
    }
    
    reader.onerror = () => reject(new Error('讀取檔案失敗'))
    reader.readAsArrayBuffer(file)
  })
}

const validateFrontend = (data: any[]): any[] => {
  const errors: any[] = []
  
  data.forEach((item, _index) => {
    const row = item.row_number
    
    // 檢查必填欄位
    if (!item.route_no) {
      errors.push({ row, field: '路線編號', message: '路線編號不能為空' })
    }
    if (!item.direction) {
      errors.push({ row, field: '方向', message: '方向不能為空' })
    }
    if (!item.date) {
      errors.push({ row, field: '日期', message: '日期不能為空' })
    }
    if (!item.departure_time) {
      errors.push({ row, field: '發車時間', message: '發車時間不能為空' })
    }
    if (!item.license_plate) {
      errors.push({ row, field: '牌照號碼', message: '牌照號碼不能為空' })
    }
    if (!item.driver_name) {
      errors.push({ row, field: '駕駛員姓名', message: '駕駛員姓名不能為空' })
    }
    if (!item.employee_id) {
      errors.push({ row, field: '員工編號', message: '員工編號不能為空' })
    }
    
    // 檢查路線1,2,3是否有營運型態
    const routeNum = parseInt(item.route_no)
    if ([1, 2, 3].includes(routeNum) && !item.special_type) {
      errors.push({ row, field: '營運型態', message: '路線 1,2,3 必須填寫營運型態（平日/假日/寒暑假）' })
    }
    
    // 驗證日期格式 (YYYY-MM-DD)
    if (item.date && !/^\d{4}-\d{2}-\d{2}$/.test(item.date)) {
      errors.push({ row, field: '日期', message: '日期格式錯誤，應為 YYYY-MM-DD' })
    }
    
    // 驗證時間格式 (HH:MM 或 HH:MM:SS)
    if (item.departure_time && !/^\d{2}:\d{2}(:\d{2})?$/.test(item.departure_time)) {
      errors.push({ row, field: '發車時間', message: '時間格式錯誤，應為 HH:MM 或 HH:MM:SS' })
    }
    
    // 驗證方向值
    if (item.direction && !['去程', '回程'].includes(item.direction)) {
      errors.push({ row, field: '方向', message: '方向必須為「去程」或「回程」' })
    }
    
    // 驗證營運型態值（如果有填）
    if (item.special_type && !['平日', '假日', '寒暑假'].includes(item.special_type)) {
      errors.push({ row, field: '營運型態', message: '營運型態必須為「平日」、「假日」或「寒暑假」' })
    }
  })
  
  return errors
}

const validateBackend = async (data: any[]) => {
  try {
    const response = await fetch('/api/schedules/batch/validate', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${getAuthToken()}`
      },
      body: JSON.stringify({ schedules: data })
    })
    
    if (!response.ok) {
      throw new Error('驗證請求失敗')
    }
    
    const result = await response.json()
    batchValidationResult.value = result
  } catch (error: any) {
    console.error('後端驗證錯誤:', error)
    alert('驗證時發生錯誤: ' + error.message)
    removeBatchFile()
  } finally {
    batchValidating.value = false
  }
}

const confirmBatchCreate = async () => {
  if (!canConfirmBatch.value || !batchData.value.length) return
  
  batchCreating.value = true
  
  try {
    const response = await fetch('/api/schedules/batch/create', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${getAuthToken()}`
      },
      body: JSON.stringify({ schedules: batchData.value })
    })
    
    if (!response.ok) {
      const error = await response.json()
      throw new Error(error.detail || '批次新增失敗')
    }
    
    const result = await response.json()
    alert(`成功新增 ${result.created_count} 筆排班資料`)
    closeBatchModal()
    fetchSchedules()
  } catch (error: any) {
    console.error('批次新增錯誤:', error)
    alert('批次新增失敗: ' + error.message)
  } finally {
    batchCreating.value = false
  }
}

const downloadTemplate = () => {
  // 建立範本資料（使用特殊前綴避免 Excel 自動轉換）
  const templateData = [
    {
      '路線編號': '1',
      '方向': '去程',
      '營運型態': '平日',
      '日期': '2025-01-09',  // 使用當前年份的日期
      '發車時間': '08:00:00',
      '牌照號碼': 'ABS-001',
      '駕駛員姓名': 'TEST01',
      '員工編號': 'T0001'
    },
    {
      '路線編號': '2',
      '方向': '去程',
      '營運型態': '平日',
      '日期': '2025-01-09',
      '發車時間': '09:00:00',
      '牌照號碼': 'ABS-002',
      '駕駛員姓名': 'TEST02',
      '員工編號': 'T0002'
    },
    {
      '路線編號': '3',
      '方向': '去程',
      '營運型態': '平日',
      '日期': '2025-01-09',
      '發車時間': '10:00:00',
      '牌照號碼': 'ABS-003',
      '駕駛員姓名': 'TEST03',
      '員工編號': 'T0003'
    }
  ]
  
  // 建立工作簿
  const worksheet = XLSX.utils.json_to_sheet(templateData)
  const workbook = XLSX.utils.book_new()
  XLSX.utils.book_append_sheet(workbook, worksheet, '排班資料')
  
  // 設定欄位寬度
  worksheet['!cols'] = [
    { wch: 10 },  // 路線編號
    { wch: 8 },   // 方向
    { wch: 10 },  // 營運型態
    { wch: 14 },  // 日期（加寬）
    { wch: 12 },  // 發車時間
    { wch: 12 },  // 牌照號碼
    { wch: 12 },  // 駕駛員姓名
    { wch: 10 }   // 員工編號
  ]
  
  // 強制將日期和時間欄位設定為文字格式
  // Excel 的欄位命名：A=0, B=1, C=2, D=3(日期), E=4(時間)
  const range = XLSX.utils.decode_range(worksheet['!ref'] || 'A1')
  
  for (let row = range.s.r + 1; row <= range.e.r; row++) {
    // 日期欄位 (D欄，索引3)
    const dateCellRef = XLSX.utils.encode_cell({ r: row, c: 3 })
    if (worksheet[dateCellRef]) {
      worksheet[dateCellRef].t = 's'  // 設定為字串類型
      worksheet[dateCellRef].z = '@'   // 設定格式為文字
    }
    
    // 發車時間欄位 (E欄，索引4)
    const timeCellRef = XLSX.utils.encode_cell({ r: row, c: 4 })
    if (worksheet[timeCellRef]) {
      worksheet[timeCellRef].t = 's'  // 設定為字串類型
      worksheet[timeCellRef].z = '@'   // 設定格式為文字
    }
    
    // 路線編號欄位 (A欄，索引0)
    const routeCellRef = XLSX.utils.encode_cell({ r: row, c: 0 })
    if (worksheet[routeCellRef]) {
      worksheet[routeCellRef].t = 's'  // 設定為字串類型
      worksheet[routeCellRef].z = '@'   // 設定格式為文字
    }
    
    // 員工編號欄位 (H欄，索引7)
    const empCellRef = XLSX.utils.encode_cell({ r: row, c: 7 })
    if (worksheet[empCellRef]) {
      worksheet[empCellRef].t = 's'  // 設定為字串類型
      worksheet[empCellRef].z = '@'   // 設定格式為文字
    }
  }
  
  // 下載檔案
  XLSX.writeFile(workbook, '排班批次新增範本.xlsx', { 
    bookType: 'xlsx',
    type: 'binary',
    cellStyles: true  // 啟用儲存格樣式
  })
}




// 分頁操作
const changePage = (page: number) => {
  if (page < 1 || page > pagination.value.pages) return
  pagination.value.page = page
  fetchSchedules()
}

const getPageNumbers = () => {
  const current = pagination.value.page
  const total = pagination.value.pages
  const pages: number[] = []
  
  const start = Math.max(1, current - 2)
  const end = Math.min(total, current + 2)
  
  for (let i = start; i <= end; i++) {
    pages.push(i)
  }
  
  return pages
}

const refresh = () => {
  pagination.value.page = 1
  pagination.value.limit = parseInt(pageSize.value.toString())
  fetchSchedules()
}

// 清除所有篩選
const clearFilters = () => {
  keyword.value = ''
  filters.value = {
    route_no: '',
    operation_status: '',
    date_from: '',
    date_to: '',
    time_from: '',
    time_to: ''
  }
  refresh()
}

// 生命週期
onMounted(() => {
  fetchSchedules()
  fetchRoutes()
  fetchCars()
  fetchDrivers()
})
</script>

<style scoped>
/* 沿用RouteManagement的完整樣式 */
.route-management {
  padding: 20px;
  min-height: 100vh;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 24px;
  background: white;
  padding: 24px;
  border-radius: 12px;
  box-shadow: 0 2px 10px rgba(0, 0, 0, 0.1);
}

.header-left h1 {
  margin: 0 0 8px 0;
  color: #2c3e50;
  font-size: 28px;
  font-weight: 600;
}

.header-left p {
  margin: 0;
  color: #6c757d;
  font-size: 14px;
}

.btn-primary {
  background: linear-gradient(135deg, #007bff 0%, #0056b3 100%);
  color: white;
  border: none;
  padding: 12px 20px;
  border-radius: 8px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 8px;
  transition: all 0.3s ease;
}

.btn-primary:hover:not(:disabled) {
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(0, 123, 255, 0.3);
}

.btn-primary:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.btn-create {
  background: linear-gradient(135deg, #10b981 0%, #059669 100%);
  color: white;
  border: none;
  padding: 12px 24px;
  border-radius: 8px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.3s ease;
  box-shadow: 0 2px 4px rgba(16, 185, 129, 0.2);
}

.btn-create:hover:not(:disabled) {
  background: linear-gradient(135deg, #059669 0%, #047857 100%);
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(16, 185, 129, 0.4);
}

.btn-create:disabled {
  opacity: 0.5;
  cursor: not-allowed;
  transform: none;
}

.btn-batch {
  background: linear-gradient(135deg, #8b5cf6 0%, #7c3aed 100%);
  color: white;
  border: none;
  padding: 12px 24px;
  border-radius: 8px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.3s ease;
  box-shadow: 0 2px 4px rgba(139, 92, 246, 0.2);
}

.btn-batch:hover:not(:disabled) {
  background: linear-gradient(135deg, #7c3aed 0%, #6d28d9 100%);
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(139, 92, 246, 0.4);
}

.btn-batch:disabled {
  opacity: 0.5;
  cursor: not-allowed;
  transform: none;
}

.header-right {
  display: flex;
  gap: 12px;
  align-items: center;
}

.filters-section {
  background: white;
  padding: 20px;
  border-radius: 12px;
  margin-bottom: 20px;
  box-shadow: 0 2px 10px rgba(0, 0, 0, 0.1);
}

.search-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
  padding-bottom: 16px;
  border-bottom: 1px solid #e9ecef;
}

.search-container {
  flex: 1;
  max-width: 400px;
}

.search-input-wrapper {
  position: relative;
  width: 100%;
}

.search-icon {
  position: absolute;
  left: 12px;
  top: 50%;
  transform: translateY(-50%);
  color: #6c757d;
  font-size: 16px;
}

.search-input {
  width: 100%;
  padding: 12px 12px 12px 40px;
  border: 2px solid #e9ecef;
  border-radius: 8px;
  font-size: 14px;
  transition: border-color 0.2s ease;
}

.search-input:focus {
  outline: none;
  border-color: #007bff;
  box-shadow: 0 0 0 3px rgba(0, 123, 255, 0.1);
}

.filter-controls {
  display: flex;
  gap: 20px;
  align-items: center;
  flex-wrap: wrap;
}

.filter-controls-row {
  display: flex;
  gap: 20px;
  align-items: flex-end;
  flex-wrap: wrap;
  margin-bottom: 16px;
}

.filter-bottom-row {
  display: flex;
  gap: 20px;
  align-items: center;
  flex-wrap: wrap;
  padding-top: 16px;
  border-top: 1px solid #e9ecef;
}

.filter-group {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 120px;
}

.filter-group-time {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 240px;
}

.range-container {
  display: flex;
  align-items: center;
  gap: 8px;
}

.range-separator {
  color: #6c757d;
  font-size: 14px;
  white-space: nowrap;
}

.filter-label {
  font-size: 14px;
  font-weight: 500;
  color: #495057;
  white-space: nowrap;
  margin-bottom: 4px;
}

.page-size-select {
  padding: 8px 12px;
  border: 2px solid #e9ecef;
  border-radius: 6px;
  font-size: 14px;
  background: white;
  cursor: pointer;
  transition: border-color 0.2s ease;
}

.page-size-select:focus {
  outline: none;
  border-color: #007bff;
}

.date-input {
  min-width: 110px;
  flex: 1;
}

.time-input {
  min-width: 110px;
  flex: 1;
}

.btn-clear-filters {
  background: #d4d4d4ff;
  color: black;
  border: none;
  padding: 8px 12px;
  border-radius: 6px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  display: flex;
  align-items: center;
  height: 38px;
  min-width: 80px;
  justify-content: center;
}

.btn-clear-filters:hover {
  background: #969595ff;
}

.table-container {
  background: white;
  border-radius: 12px;
  overflow: hidden;
  box-shadow: 0 2px 10px rgba(0, 0, 0, 0.1);
}

.admin-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 14px;
}

.admin-table th {
  background: linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%);
  padding: 16px 12px;
  text-align: left;
  font-weight: 600;
  color: #495057;
  border-bottom: 1px solid #dee2e6;
}

.admin-table td {
  padding: 16px 12px;
  border-bottom: 1px solid #f1f3f4;
  vertical-align: middle;
}

.table-row:hover {
  background: rgba(0, 123, 255, 0.05);
}

.route-cell, .license-cell {
  font-weight: 500;
}

.route-name, .license-plate {
  color: #007bff;
  font-weight: 600;
}

.direction-badge {
  background: #e3f2fd;
  color: #1976d2;
  padding: 4px 8px;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 500;
}

.status-badge {
  padding: 4px 8px;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 500;
}

.status-active {
  background: #d4edda;
  color: #155724;
}

.status-warning {
  background: #fff3cd;
  color: #856404;
}

.status-danger {
  background: #f8d7da;
  color: #721c24;
}

.status-secondary {
  background: #e2e3e5;
  color: #383d41;
}

.actions-cell {
  width: 120px;
}

.action-buttons {
  display: flex;
  gap: 8px;
}

.btn-edit, .btn-delete {
  width: 32px;
  height: 32px;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  font-size: 14px;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s ease;
}

.btn-edit {
  background: #dbeafe;
  color: #1e40af;
}

.btn-edit:hover {
  background: #bfdbfe;
  transform: translateY(-1px);
}

.btn-delete {
  background: #fecaca;
  color: #991b1b;
}

.btn-delete:hover:not(:disabled) {
  background: #fca5a5;
  transform: translateY(-1px);
}

.btn-edit:disabled, .btn-delete:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.empty-state {
  text-align: center;
  padding: 60px 20px;
  color: #6c757d;
}

.empty-icon {
  font-size: 48px;
  margin-bottom: 16px;
}

.empty-state h3 {
  margin: 0 0 8px 0;
  color: #495057;
}

.loading-state {
  text-align: center;
  padding: 40px 20px;
  color: #6c757d;
}

.loading-spinner {
  width: 32px;
  height: 32px;
  border: 3px solid #f3f3f3;
  border-top: 3px solid #007bff;
  border-radius: 50%;
  animation: spin 1s linear infinite;
  margin: 0 auto 16px;
}

@keyframes spin {
  0% { transform: rotate(0deg); }
  100% { transform: rotate(360deg); }
}

.pagination-container {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 20px;
  padding: 16px 24px;
  background: white;
  border-radius: 12px;
  box-shadow: 0 2px 10px rgba(0, 0, 0, 0.1);
}

.pagination-info {
  font-size: 14px;
  color: #6c757d;
}

.pagination-controls {
  display: flex;
  align-items: center;
  gap: 8px;
}

.pagination-btn {
  padding: 8px 16px;
  border: 1px solid #dee2e6;
  background: white;
  border-radius: 6px;
  cursor: pointer;
  font-size: 14px;
  transition: all 0.2s ease;
}

.pagination-btn:hover:not(:disabled) {
  background: #f8f9fa;
  border-color: #007bff;
}

.pagination-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.pagination-numbers {
  display: flex;
  gap: 4px;
}

.pagination-number {
  width: 36px;
  height: 36px;
  border: 1px solid #dee2e6;
  background: white;
  border-radius: 6px;
  cursor: pointer;
  font-size: 14px;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s ease;
}

.pagination-number:hover {
  background: #f8f9fa;
  border-color: #007bff;
}

.pagination-number.active {
  background: #007bff;
  color: white;
  border-color: #007bff;
}

/* 模態框樣式 */
.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.modal-content {
  background: white;
  border-radius: 12px;
  width: 90%;
  max-width: 800px;
  max-height: 90vh;
  overflow-y: auto;
  box-shadow: 0 10px 30px rgba(0, 0, 0, 0.2);
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 24px;
  border-bottom: 1px solid #e9ecef;
}

.modal-header h2 {
  margin: 0;
  color: #2c3e50;
  font-size: 20px;
}

.close-btn {
  background: none;
  border: none;
  font-size: 24px;
  cursor: pointer;
  color: #6c757d;
  padding: 0;
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 6px;
  transition: all 0.2s ease;
}

.close-btn:hover {
  background: #f8f9fa;
  color: #495057;
}

.modal-form {
  padding: 24px;
}

.form-content {
  margin-bottom: 24px;
}

.form-row {
  display: flex;
  gap: 16px;
  margin-bottom: 16px;
}

.form-group {
  flex: 1;
  display: flex;
  flex-direction: column;
}

.form-group.full-width {
  flex: 100%;
}

.form-label {
  margin-bottom: 8px;
  font-weight: 500;
  color: #495057;
  font-size: 14px;
}

.required {
  color: #dc3545;
}

.form-input, .form-select {
  padding: 12px;
  border: 2px solid #e9ecef;
  border-radius: 6px;
  font-size: 14px;
  transition: border-color 0.2s ease;
}

.form-input:focus, .form-select:focus {
  outline: none;
  border-color: #007bff;
  box-shadow: 0 0 0 3px rgba(0, 123, 255, 0.1);
}

/* 只讀欄位樣式 */
.readonly-field {
  background: #f8f9fa !important;
  color: #6c757d !important;
  cursor: not-allowed !important;
  border-color: #dee2e6 !important;
}

.readonly-indicator {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  color: #6c757d;
  margin-top: 4px;
  font-style: italic;
}

.form-actions {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  padding-top: 24px;
  border-top: 1px solid #e9ecef;
}

.btn-secondary {
  background: #6c757d;
  color: white;
  border: none;
  padding: 12px 20px;
  border-radius: 8px;
  font-size: 14px;
  cursor: pointer;
  transition: all 0.2s ease;
}

.btn-secondary:hover {
  background: #5a6268;
  transform: translateY(-1px);
}

.btn-danger {
  background: #dc3545;
  color: white;
  border: none;
  padding: 12px 20px;
  border-radius: 8px;
  font-size: 14px;
  cursor: pointer;
  transition: all 0.2s ease;
}

.btn-danger:hover:not(:disabled) {
  background: #c82333;
  transform: translateY(-1px);
}

.btn-danger:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.delete-modal {
  max-width: 500px;
}

.modal-body {
  padding: 20px 24px;
}

.delete-info {
  background: #f8f9fa;
  padding: 16px;
  border-radius: 8px;
  margin: 16px 0;
  border-left: 4px solid #dc3545;
}

.delete-info p {
  margin: 4px 0;
  font-size: 14px;
}

.warning-text {
  color: #dc3545;
  font-weight: 500;
  font-size: 14px;
  margin-top: 16px !important;
}

@media (max-width: 768px) {
  .route-management {
    padding: 10px;
  }
  
  .page-header {
    flex-direction: column;
    align-items: flex-start;
    gap: 16px;
  }
  
  .search-row {
    flex-direction: column;
    align-items: stretch;
    gap: 12px;
  }
  
  .filter-controls-row {
    flex-direction: column;
    align-items: stretch;
    gap: 16px;
  }
  
  .filter-bottom-row {
    flex-direction: column;
    align-items: stretch;
    gap: 16px;
  }
  
  .filter-group, .filter-group-time {
    min-width: unset;
    width: 100%;
  }
  
  .range-container {
    flex-direction: column;
    align-items: stretch;
    gap: 8px;
  }
  
  .range-separator {
    text-align: center;
  }
  
  .form-row {
    flex-direction: column;
  }
  
  .pagination-container {
    flex-direction: column;
    gap: 16px;
  }
  
  .admin-table {
    font-size: 12px;
  }
  
  .admin-table th,
  .admin-table td {
    padding: 8px;
  }
}

/* 批次新增相關樣式 */
.batch-modal {
  max-width: 900px;
  width: 90%;
}

.upload-section {
  margin-bottom: 20px;
}

.upload-area {
  border: 2px dashed #cbd5e0;
  border-radius: 8px;
  padding: 40px;
  text-align: center;
  cursor: pointer;
  transition: all 0.3s;
  background-color: #f7fafc;
}

.upload-area:hover {
  border-color: #4299e1;
  background-color: #ebf8ff;
}

.upload-area.drag-over {
  border-color: #4299e1;
  background-color: #bee3f8;
}

.upload-icon {
  font-size: 48px;
  margin-bottom: 12px;
}

.upload-text {
  font-size: 16px;
  font-weight: 500;
  color: #2d3748;
  margin-bottom: 8px;
}

.upload-hint {
  font-size: 14px;
  color: #718096;
}

.upload-actions {
  margin-top: 12px;
  text-align: center;
}

.btn-download-template {
  padding: 8px 16px;
  background-color: #f7fafc;
  color: #2d3748;
  border: 1px solid #cbd5e0;
  border-radius: 6px;
  cursor: pointer;
  font-size: 14px;
  transition: all 0.2s;
}

.btn-download-template:hover {
  background-color: #edf2f7;
  border-color: #a0aec0;
}

.file-info {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px;
  background-color: #f7fafc;
  border-radius: 6px;
  margin-bottom: 20px;
}

.file-name {
  flex: 1;
  font-size: 14px;
  color: #2d3748;
}

.file-size {
  font-size: 13px;
  color: #718096;
}

.btn-remove-file {
  padding: 4px 8px;
  background-color: #fff;
  color: #e53e3e;
  border: 1px solid #fc8181;
  border-radius: 4px;
  cursor: pointer;
  font-size: 14px;
  transition: all 0.2s;
}

.btn-remove-file:hover {
  background-color: #fff5f5;
}

.preview-section {
  margin-bottom: 20px;
}

.preview-section h3 {
  font-size: 16px;
  font-weight: 600;
  color: #2d3748;
  margin-bottom: 12px;
}

.preview-table-wrapper {
  max-height: 300px;
  overflow: auto;
  border: 1px solid #e2e8f0;
  border-radius: 6px;
}

.preview-table {
  width: 100%;
  font-size: 13px;
  border-collapse: collapse;
}

.preview-table th {
  position: sticky;
  top: 0;
  background-color: #f7fafc;
  padding: 10px 8px;
  text-align: left;
  font-weight: 600;
  color: #2d3748;
  border-bottom: 2px solid #e2e8f0;
  white-space: nowrap;
}

.preview-table td {
  padding: 8px;
  border-bottom: 1px solid #e2e8f0;
  color: #4a5568;
  white-space: nowrap;
}

.preview-table tbody tr:hover {
  background-color: #f7fafc;
}

.validation-status {
  padding: 16px;
  border-radius: 6px;
  margin-bottom: 20px;
}

.validation-status.loading {
  background-color: #ebf8ff;
  border: 1px solid #bee3f8;
  color: #2c5282;
}

.validation-status.success {
  background-color: #f0fff4;
  border: 1px solid #9ae6b4;
  color: #22543d;
}

.validation-status.error {
  background-color: #fff5f5;
  border: 1px solid #fc8181;
  color: #742a2a;
}

.validation-status h4 {
  font-size: 15px;
  font-weight: 600;
  margin-bottom: 4px;
}

.validation-status p {
  font-size: 13px;
  margin: 0;
}

.error-list {
  max-height: 200px;
  overflow-y: auto;
  margin-top: 12px;
}

.error-item {
  padding: 8px 12px;
  background-color: #fff;
  border-left: 3px solid #fc8181;
  margin-bottom: 8px;
  border-radius: 4px;
  font-size: 13px;
}

.error-item .error-row {
  font-weight: 600;
  color: #e53e3e;
  margin-right: 8px;
}

.error-item .error-field {
  color: #2d3748;
  margin-right: 4px;
}

.error-item .error-message {
  color: #4a5568;
}

.icon-upload::before {
  content: '📤';
  margin-right: 4px;
}
</style>