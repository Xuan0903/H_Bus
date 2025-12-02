<template>
  <div class="route-management">
    <div class="page-header">
      <div class="header-left">
        <h1 class="page-title">預約管理</h1>
        <p class="page-description">管理預約資料與審核派車狀態</p>
      </div>
      <div class="header-right">
        <button class="btn-primary" @click="openCreate" :disabled="!canWrite">
          <i class="icon-plus"></i>
          新增預約
        </button>
      </div>
    </div>

    <!-- 篩選列（沿用路線 UI 配置） -->
    <div class="filters-section">
      <div class="search-container">
        <div class="search-input-wrapper">
          <span class="search-icon">🔍</span>
          <input v-model="keyword" @input="debouncedSearch" type="text" placeholder="搜尋起訖站名、用戶ID..." class="search-input" />
        </div>
      </div>

      <div class="filter-controls">
        <div class="filter-group">
          <label class="filter-label">付款狀態：</label>
          <select v-model="filters.payment_status" @change="refresh" class="page-size-select">
            <option value="">全部</option>
            <option value="pending">未付款</option>
            <option value="paid">已付款</option>
            <option value="failed">失敗</option>
            <option value="refunded">已退款</option>
          </select>
        </div>
        <div class="filter-group">
          <label class="filter-label">審核狀態：</label>
          <select v-model="filters.review_status" @change="refresh" class="page-size-select">
            <option value="">全部</option>
            <option value="pending">審核中</option>
            <option value="approved">已核准</option>
            <option value="rejected">已拒絕</option>
            <option value="canceled">已取消</option>
          </select>
        </div>
        <div class="filter-group">
          <label class="filter-label">派車狀態：</label>
          <select v-model="filters.dispatch_status" @change="refresh" class="page-size-select">
            <option value="">全部</option>
            <option value="not_assigned">未派車</option>
            <option value="assigned">已派車</option>
          </select>
        </div>
        <div class="filter-group">
          <label class="filter-label">ID排序：</label>
          <select v-model="sortOrder" @change="refresh" class="page-size-select">
            <option value="desc">由新到舊</option>
            <option value="asc">由舊到新</option>
          </select>
        </div>
        <div class="filter-group">
          <label class="filter-label">每頁顯示：</label>
          <select v-model.number="pageSize" @change="onPageSizeChange" class="page-size-select">
            <option :value="10">10 筆</option>
            <option :value="20">20 筆</option>
            <option :value="50">50 筆</option>
          </select>
        </div>
      </div>
    </div>

    <div class="table-container">
      <div v-if="loading" class="loading-overlay"><div class="spinner"></div><span>載入中...</span></div>
      <table v-else class="admin-table">
        <thead>
          <tr>
            <th>ID</th>
            <th>用戶ID</th>
            <th>預約時間</th>
            <th>人數</th>
            <th>起點</th>
            <th>終點</th>
            <th>付款</th>
            <th>審核</th>
            <th>派車</th>
            <th>建立時間</th>
            <th class="actions-column">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="r in reservations" :key="r.reservation_id" class="table-row">
            <td>{{ r.reservation_id }}</td>
            <td>{{ r.user_id ?? '-' }}</td>
            <td class="date-cell">{{ fmt(r.booking_time) }}</td>
            <td>{{ r.booking_number ?? '-' }}</td>
            <td>{{ r.booking_start_station_name ?? '-' }}</td>
            <td>{{ r.booking_end_station_name ?? '-' }}</td>
            <td><span class="status-badge" :class="r.payment_status">{{ mapPay(r.payment_status) }}</span></td>
            <td><span class="status-badge" :class="r.review_status">{{ mapReview(r.review_status) }}</span></td>
            <td><span class="status-badge" :class="r.dispatch_status">{{ mapDispatch(r.dispatch_status) }}</span></td>
            <td class="date-cell">{{ fmt(r.created_at) }}</td>
            <td class="actions-cell">
              <div class="action-buttons">
                <button class="btn-edit" title="編輯" @click.stop="openEdit(r)" :disabled="!canWrite">✏️</button>
                <button class="btn-delete" title="刪除" @click.stop="askDelete(r)" :disabled="!canWrite">🗑️</button>
              </div>
            </td>
          </tr>
        </tbody>
      </table>

      <div v-if="!loading && reservations.length === 0" class="empty-state">
        <div class="empty-icon">📅</div>
        <h3>沒有找到預約</h3>
        <p>{{ keyword ? '沒有符合搜尋條件的預約' : '目前沒有預約資料' }}</p>
      </div>
    </div>

    <!-- 分頁 -->
    <div v-if="!loading && reservations.length > 0" class="pagination-container">
      <div class="pagination-info">
        顯示第 {{ (page - 1) * pageSize + 1 }} 到 {{ Math.min(page * pageSize, total) }} 筆，共 {{ total }} 筆
      </div>
      <div class="pagination-controls">
        <button class="pagination-btn" @click="go(page-1)" :disabled="page===1">上一頁</button>
        <div class="page-numbers">
          <button v-for="p in pages" :key="p" class="page-number" :class="{active:p===page}" @click="go(p)">{{ p }}</button>
        </div>
        <button class="pagination-btn" @click="go(page+1)" :disabled="page===totalPages">下一頁</button>
      </div>
    </div>

    <!-- 新增/編輯 -->
    <div v-if="showModal" class="modal-overlay" @click="closeModal">
      <div class="modal-content" @click.stop>
        <div class="modal-header">
          <h2>{{ editMode ? '編輯預約' : '新增預約' }}</h2>
          <button class="close-btn" @click="closeModal">×</button>
        </div>
        <form @submit.prevent="save" class="modal-form">
          <!-- 編輯模式下的訂單內容區塊 -->
          <div v-if="editMode" class="order-info-section">
            <div class="section-header">
              <h3 class="section-title">確認訂單內容</h3>
              <button type="button" class="btn-modify" @click="toggleOrderEdit" :disabled="!canWrite">
                {{ isOrderEditable ? '鎖定' : '修正' }}
              </button>
            </div>
            <div class="order-info-content" :class="{ 'locked': !isOrderEditable }">
              <div class="form-row">
                <div class="form-group">
                  <label class="form-label">用戶ID</label>
                  <input v-model.number="form.user_id" type="number" class="form-input" min="1" :disabled="editMode && !isOrderEditable" />
                </div>
                <div class="form-group">
                  <label class="form-label">預約時間</label>
                  <input v-model="form.booking_time" type="datetime-local" class="form-input" :disabled="editMode && !isOrderEditable" />
                </div>
              </div>
              <div class="form-row">
                <div class="form-group">
                  <label class="form-label">人數</label>
                  <input v-model.number="form.booking_number" type="number" min="1" class="form-input" :disabled="editMode && !isOrderEditable" />
                </div>
                <div class="form-group">
                  <label class="form-label">付款方式</label>
                  <input v-model="form.payment_method" type="text" class="form-input" :disabled="editMode && !isOrderEditable" />
                </div>
              </div>
              <div class="form-row">
                <div class="form-group">
                  <label class="form-label">起點</label>
                  <input v-model="form.booking_start_station_name" type="text" class="form-input" :disabled="editMode && !isOrderEditable" />
                </div>
                <div class="form-group">
                  <label class="form-label">終點</label>
                  <input v-model="form.booking_end_station_name" type="text" class="form-input" :disabled="editMode && !isOrderEditable" />
                </div>
              </div>
            </div>
          </div>

          <!-- 新增模式下的基本資訊 -->
          <div v-if="!editMode">
            <div class="form-row">
              <div class="form-group">
                <label class="form-label">用戶ID</label>
                <input v-model.number="form.user_id" type="number" class="form-input" min="1" />
              </div>
              <div class="form-group">
                <label class="form-label">預約時間</label>
                <input v-model="form.booking_time" type="datetime-local" class="form-input" />
              </div>
            </div>
            <div class="form-row">
              <div class="form-group">
                <label class="form-label">人數</label>
                <input v-model.number="form.booking_number" type="number" min="1" class="form-input" />
              </div>
              <div class="form-group">
                <label class="form-label">付款方式</label>
                <input v-model="form.payment_method" type="text" class="form-input" />
              </div>
            </div>
            <div class="form-row">
              <div class="form-group">
                <label class="form-label">起點</label>
                <input v-model="form.booking_start_station_name" type="text" class="form-input" />
              </div>
              <div class="form-group">
                <label class="form-label">終點</label>
                <input v-model="form.booking_end_station_name" type="text" class="form-input" />
              </div>
            </div>
          </div>

          <!-- 狀態管理區塊 -->
          <div class="status-section">
            <div v-if="editMode" class="section-header">
              <h3 class="section-title">狀態管理</h3>
            </div>
            <div class="form-row">
              <div class="form-group">
                <label class="form-label">付款狀態</label>
                <div class="payment-status-display">
                  <span class="status-badge" :class="form.payment_status">{{ mapPay(form.payment_status) }}</span>
                  <small class="status-note">從資料庫讀取，無法手動修改</small>
                </div>
              </div>
              <div class="form-group">
                <label class="form-label">審核狀態</label>
                <select v-model="form.review_status" class="form-select">
                  <option value="pending">審核中</option>
                  <option value="approved">已核准</option>
                  <option value="rejected">已拒絕</option>
                  <option value="canceled">已取消</option>
                </select>
              </div>
            </div>
            <div 
              v-if="editMode && form.review_status === 'canceled'" 
              class="form-row lock-notice"
            >
              <div class="form-group full-width">
                <label class="form-label">取消原因</label>
                <span class="notice-text">{{ form.cancel_reason || '無' }}</span>
              </div>
            </div>
            <div class="form-row">
              <div class="form-group">
                <label class="form-label">派車狀態</label>
                <select v-model="form.dispatch_status" class="form-select">
                  <option value="not_assigned">未派車</option>
                  <option value="assigned">已派車</option>
                </select>
              </div>
              <div class="form-group full-width">
                <label class="form-label">付款紀錄</label>
                <textarea 
                  v-model="form.payment_record" 
                  class="form-textarea" 
                  :class="{ 'readonly-field': editMode }"
                  :readonly="editMode"
                  rows="3"
                ></textarea>
              </div>
            </div>
          </div>

          <div class="form-actions">
            <button type="button" class="btn-secondary" @click="closeModal">取消</button>
            <button type="submit" class="btn-primary" :disabled="saving">
              {{ saving ? '儲存中...' : (editMode ? (isOrderEditable ? '更新' : '更新狀態') : '新增') }}
            </button>
          </div>
          
          <!-- 鎖定狀態提示 -->
          <div v-if="editMode && !isOrderEditable" class="lock-notice">
            <div class="notice-content">
              <span class="notice-icon">🔒</span>
              <span class="notice-text">訂單基本資訊已鎖定，僅可修改狀態管理欄位。如需修正訂單內容，請點擊上方「修正」按鈕。</span>
            </div>
          </div>
        </form>
      </div>
    </div>

    <!-- 刪除確認 -->
    <div v-if="showDelete" class="modal-overlay" @click="cancelDelete">
      <div class="modal-content delete-modal" @click.stop>
        <div class="modal-header">
          <h2>確認刪除</h2>
          <button class="close-btn" @click="cancelDelete">×</button>
        </div>
        <div class="modal-body">
          <p>確定要刪除預約「{{ toDelete?.reservation_id }}」嗎？</p>
          <p class="warning-text">此操作無法復原。</p>
        </div>
        <div class="form-actions">
          <button class="btn-secondary" @click="cancelDelete">取消</button>
          <button class="btn-danger" @click="confirmDelete" :disabled="deleting">{{ deleting ? '刪除中...' : '確認刪除' }}</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'

const loading = ref(false)
const saving = ref(false)
const deleting = ref(false)
const reservations = ref<any[]>([])
const page = ref(1)
const pageSize = ref(10)
const total = ref(0)
const totalPages = computed(() => Math.ceil(total.value / pageSize.value) || 1)
const keyword = ref('')
const filters = ref({ payment_status: '', review_status: '', dispatch_status: '' })
const sortOrder = ref<'desc' | 'asc'>('desc')

// 權限：僅 super_admin 與 admin 可寫入
const currentUser = ref<any>(null)
const role = computed(() => (currentUser.value?.role || '').toLowerCase())
const canWrite = computed(() => role.value === 'super_admin' || role.value === 'admin')

// 分頁顯示
const pages = computed(() => {
  const ps:number[] = []
  const max = 5
  let s = Math.max(1, page.value - 2)
  let e = Math.min(totalPages.value, s + max - 1)
  if (e - s + 1 < max) s = Math.max(1, e - max + 1)
  for (let i = s; i <= e; i++) ps.push(i)
  return ps
})

function fmt(v: any){
  if(!v) return '-'
  try { return new Date(v).toLocaleString('zh-TW') } catch { return String(v) }
}
function mapPay(s: string){ return ({pending:'未付款',paid:'已付款',failed:'失敗',refunded:'已退款'} as any)[s] || s }
function mapReview(s: string){ return ({pending:'審核中',approved:'已核准',rejected:'已拒絕',canceled:'已取消'} as any)[s] || s }
function mapDispatch(s: string){ return ({not_assigned:'未派車',assigned:'已派車'} as any)[s] || s }

async function fetchList(){
  loading.value = true
  try {
    const params = new URLSearchParams()
    params.append('page', String(page.value))
    params.append('limit', String(pageSize.value))
    if (keyword.value.trim()) params.append('search', keyword.value.trim())
    if (filters.value.payment_status) params.append('payment_status', filters.value.payment_status)
    if (filters.value.review_status) params.append('review_status', filters.value.review_status)
    if (filters.value.dispatch_status) params.append('dispatch_status', filters.value.dispatch_status)
    if (sortOrder.value) params.append('order', sortOrder.value)
    const res = await fetch(`/api/reservations?${params.toString()}`, { headers: { 'Authorization': `Bearer ${localStorage.getItem('token') || ''}` } })
    const data = await res.json()
    if (data.success){
      reservations.value = data.data || []
      total.value = data.pagination?.total || 0
    } else {
      reservations.value = []
      total.value = 0
    }
  } finally {
    loading.value = false
  }
}

let timer: any = null
function debouncedSearch(){
  if (timer) clearTimeout(timer)
  timer = setTimeout(() => { page.value = 1; fetchList() }, 500)
}
function onPageSizeChange(){ page.value = 1; fetchList() }
function refresh(){ page.value = 1; fetchList() }
function go(p:number){ if (p>=1 && p<=totalPages.value){ page.value = p; fetchList() } }

const showModal = ref(false)
const editMode = ref(false)
const isOrderEditable = ref(false) // 控制訂單內容是否可編輯
const form = ref<any>({
  user_id: null,
  booking_time: '',
  booking_number: null,
  booking_start_station_name: '',
  booking_end_station_name: '',
  payment_method: '',
  payment_record: '',
  payment_status: 'pending',
  review_status: 'pending',
  dispatch_status: 'not_assigned',
})

function openCreate(){ if(!canWrite.value) return; editMode.value=false; isOrderEditable.value=true; resetForm(); showModal.value=true }
function openEdit(r:any){ 
  if(!canWrite.value) return; 
  editMode.value=true; 
  isOrderEditable.value=false; 
  form.value = { ...r, booking_time: toLocalInput(r.booking_time) }
  showModal.value=true 
}
function closeModal(){ showModal.value=false; editMode.value=false; isOrderEditable.value=false }
function toggleOrderEdit(){ isOrderEditable.value = !isOrderEditable.value }
function resetForm(){
  form.value = { user_id:null, booking_time:'', booking_number:null, booking_start_station_name:'', booking_end_station_name:'', payment_method:'', payment_record:'', payment_status:'pending', review_status:'pending', dispatch_status:'not_assigned' }
}
function toLocalInput(v:any){
  if (!v) return ''
  const d = new Date(v)
  const pad=(n:number)=> String(n).padStart(2,'0')
  return `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`
}

async function save(){
  if(!canWrite.value) return
  saving.value = true
  try{
    let payload = { ...form.value }
    
    // 如果是編輯模式且訂單內容被鎖定，則排除訂單基本資訊欄位
    if (editMode.value && !isOrderEditable.value) {
      // 只保留可編輯的狀態管理欄位（移除 payment_record）
      const editableFields = ['review_status', 'dispatch_status']
      const statusPayload: any = { reservation_id: form.value.reservation_id }
      
      editableFields.forEach(field => {
        if (form.value[field] !== undefined) {
          statusPayload[field] = form.value[field]
        }
      })
      
      payload = statusPayload
    }
    
    if (!payload.booking_time) delete payload.booking_time
    const url = editMode.value ? `/api/reservations/${form.value.reservation_id}` : '/api/reservations'
    const method = editMode.value ? 'PUT' : 'POST'
    const res = await fetch(url, { method, headers: { 'Content-Type':'application/json', 'Authorization': `Bearer ${localStorage.getItem('token') || ''}` }, body: JSON.stringify(payload) })
    const data = await res.json().catch(()=> ({}))
    if (!res.ok || data?.success === false) { alert(data?.detail || data?.message || '處理失敗'); return }
    closeModal(); fetchList(); alert('處理成功')
  } finally { saving.value=false }
}

const showDelete = ref(false)
const toDelete = ref<any>(null)
function askDelete(r:any){ if(!canWrite.value) return; toDelete.value=r; showDelete.value=true }
function cancelDelete(){ showDelete.value=false; toDelete.value=null }
async function confirmDelete(){
  if(!toDelete.value) return
  deleting.value = true
  try{
    const res = await fetch(`/api/reservations/${toDelete.value.reservation_id}`, { method:'DELETE', headers:{ 'Authorization': `Bearer ${localStorage.getItem('token') || ''}` } })
    const data = await res.json().catch(()=> ({}))
    if (!res.ok || data?.success === false) { alert(data?.detail || data?.message || '刪除失敗'); return }
    showDelete.value=false; toDelete.value=null; fetchList(); alert('刪除成功')
  } finally { deleting.value=false }
}

onMounted(() => {
  try { const u = localStorage.getItem('user'); if (u) currentUser.value = JSON.parse(u) } catch {}
  fetchList()
})
</script>

<style scoped>
/* 使用與 RouteManagement.vue 相同的樣式（複製核心樣式確保一致） */
.route-management { padding: 24px; background-color: #f8f9fa; min-height: calc(100vh - 60px); }
.page-header { display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:32px; padding:24px; background:white; border-radius:12px; box-shadow:0 2px 8px rgba(0,0,0,.1); }
.header-left h1 { color:#2c3e50; margin:0 0 8px 0; font-size:28px; font-weight:600; }
.header-left p { color:#6c757d; margin:0; font-size:14px; }
.header-right { display:flex; align-items:center; gap:12px; }
.btn-primary { background: linear-gradient(135deg, #007bff 0%, #0056b3 100%); color:white; border:none; padding:12px 20px; border-radius:8px; cursor:pointer; font-weight:500; display:flex; align-items:center; gap:8px; transition:all .2s ease; font-size:14px; }
.btn-primary:hover { background: linear-gradient(135deg, #0056b3 0%, #004085 100%); transform: translateY(-1px); box-shadow: 0 4px 12px rgba(0,123,255,.3); }
.filters-section { background:white; padding:20px 24px; border-radius:12px; box-shadow:0 2px 8px rgba(0,0,0,.1); margin-bottom:24px; display:flex; justify-content:space-between; align-items:center; gap:20px; }
.search-container { flex:1; max-width:400px; }
.search-input-wrapper { position:relative; }
.search-icon { position:absolute; left:12px; top:50%; transform:translateY(-50%); color:#6c757d; font-size:16px; }
.search-input { width:100%; padding:10px 16px 10px 40px; border:2px solid #e9ecef; border-radius:8px; font-size:14px; transition:border-color .2s ease; }
.search-input:focus { outline:none; border-color:#007bff; box-shadow:0 0 0 3px rgba(0,123,255,.1); }
.filter-controls { display:flex; gap:20px; align-items:center; }
.filter-group { display:flex; align-items:center; gap:8px; }
.filter-label { color:#495057; font-weight:500; font-size:14px; white-space:nowrap; }
.page-size-select { padding:8px 12px; border:2px solid #e9ecef; border-radius:6px; font-size:14px; background:white; cursor:pointer; transition:border-color .2s ease; }
.page-size-select:focus { outline:none; border-color:#007bff; }
.table-container { background:white; border-radius:16px; box-shadow:0 4px 16px rgba(0,0,0,.08); border:1px solid #e5e7eb; position:relative; margin-bottom:24px; max-height:600px; overflow:auto; }
.admin-table { width:100%; border-collapse:collapse; min-width:1000px; }
.admin-table th { background:#f8f9fa; padding:16px 12px; text-align:left; font-weight:600; color:#495057; border-bottom:2px solid #e9ecef; font-size:14px; position:sticky; top:0; z-index:1; }
.admin-table td { padding:16px 12px; border-bottom:1px solid #e9ecef; font-size:14px; white-space:nowrap; }
.table-row:hover { background:#f8f9fa; }
.status-badge { display:inline-block; padding:4px 10px; border-radius:12px; font-size:12px; font-weight:600; }
.status-badge.pending { background:#fff3cd; color:#856404; }
.status-badge.paid { background:#d4edda; color:#155724; }
.status-badge.failed { background:#f8d7da; color:#721c24; }
.status-badge.refunded { background:#e2e3e5; color:#343a40; }
.status-badge.approved { background:#cfe2ff; color:#084298; }
.status-badge.rejected { background:#f8d7da; color:#721c24; }
.status-badge.canceled { background:#eee; color:#6b7280; }
.status-badge.assigned { background:#e0f2fe; color:#075985; }
.status-badge.not_assigned { background:#e9ecef; color:#495057; }
.actions-cell { text-align:center; }
.action-buttons { display:flex; justify-content:center; gap:8px; }
.btn-edit, .btn-delete { display:inline-flex; align-items:center; justify-content:center; width:36px; height:36px; border:none; border-radius:8px; cursor:pointer; font-size:14px; transition: all .3s ease; }
.btn-edit { background:#dbeafe; color:#1e40af; }
.btn-delete { background:#fecaca; color:#991b1b; }
.btn-edit:hover { background:#bfdbfe; transform: translateY(-1px); }
.btn-delete:hover { background:#fca5a5; transform: translateY(-1px); }
.empty-state { text-align:center; padding:64px 24px; color:#6b7280; }
.empty-icon { font-size:64px; margin-bottom:16px; opacity:.5; }
.pagination-container { display:flex; justify-content:space-between; align-items:center; background:white; padding:20px 24px; border-radius:16px; box-shadow:0 2px 8px rgba(0,0,0,.06); border:1px solid #e5e7eb; }
.pagination-info { color:#6b7280; font-size:14px; }
.pagination-controls { display:flex; align-items:center; gap:8px; }
.pagination-btn { padding:8px 16px; border:2px solid #e2e8f0; background:white; color:#374151; border-radius:8px; font-size:14px; font-weight:600; cursor:pointer; transition:all .3s ease; }
.pagination-btn:hover { background:#f8fafc; border-color:#3b82f6; color:#3b82f6; }
.page-numbers { display:flex; gap:4px; margin:0 8px; }
.page-number { display:flex; align-items:center; justify-content:center; width:36px; height:36px; border:2px solid transparent; background:white; color:#374151; border-radius:8px; font-size:14px; font-weight:600; cursor:pointer; transition:all .3s ease; }
.page-number.active { background:#3b82f6; color:white; border-color:#3b82f6; }

.modal-overlay { position:fixed; inset:0; background:rgba(0,0,0,.6); display:flex; align-items:center; justify-content:center; z-index:1000; padding:24px; }
.modal-content { background:white; border-radius:12px; max-width:600px; width:90%; max-height:90vh; overflow-y:auto; box-shadow: 0 4px 20px rgba(0, 0, 0, 0.15);}
.modal-header { display:flex; justify-content:space-between; align-items:center; padding:20px 24px; border-bottom:1px solid #e9ecef; }
.modal-header h2 {margin: 0; color: #2c3e50; font-size: 20px; font-weight: 600;}
.close-btn { display:flex; align-items:center; justify-content:center; width:32px; height:32px; border:none; background:#f3f4f6; color:#6b7280; border-radius:50%; cursor:pointer; font-size:24px; }
.btn-close {background: none; border: none; font-size: 24px; cursor: pointer; color: #6c757d; padding: 0; width: 32px; height: 32px; display: flex; align-items: center; justify-content: center; border-radius: 50%; transition: all 0.2s ease;}
.btn-close:hover {background: #f8f9fa; color: #495057;}
.modal-form { padding:24px; }
.form-row { display:flex; gap:20px; margin-bottom:20px; }
.form-group { flex:1; display:flex; flex-direction:column; }
.form-group.full-width { flex-basis:100%; }
.form-label { margin-bottom:6px; font-weight:500; color:#495057; font-size:14px; }
.form-input, .form-select, .form-textarea { padding:10px 12px; border:2px solid #e9ecef; border-radius:6px; font-size:14px; transition:border-color .2s ease; }
.form-textarea { resize:vertical; }
.form-input:focus, .form-select:focus, .form-textarea:focus { outline:none; border-color:#007bff; box-shadow:0 0 0 3px rgba(0,123,255,.1); }
.form-actions { display:flex; gap:12px; justify-content:center; padding: 0 24px 24px;}
.btn-secondary { padding:10px 20px; border:2px solid #6c757d; background:white; color:#6c757d; border-radius:6px; cursor:pointer; font-size:14px; font-weight:500; transition:all .2s ease; }
.btn-secondary:hover { background:#6c757d; color:white; }
.btn-danger { padding:10px 20px; border:2px solid #dc3545; background:#dc3545; color:white; border-radius:6px; cursor:pointer; font-size:14px; font-weight:500; transition:all .2s ease; }
.btn-danger:hover { background:#c82333; border-color:#c82333; }
.delete-modal { max-width:400px; }
.modal-body { padding:24px; text-align:center; }
.warning-text { color:#dc2626; font-weight:500; margin-top:8px; }

/* 新增樣式 */
.order-info-section {
  background: #f8f9fa;
  border: 1px solid #e9ecef;
  border-radius: 8px;
  margin-bottom: 24px;
  overflow: hidden;
}

.status-section {
  background: white;
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 20px;
  background: #ffffff;
  border-bottom: 1px solid #e9ecef;
}

.section-title {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: #495057;
}

.btn-modify {
  padding: 6px 12px;
  border: 2px solid #6c757d;
  background: white;
  color: #6c757d;
  border-radius: 6px;
  cursor: pointer;
  font-size: 12px;
  font-weight: 500;
  transition: all 0.2s ease;
}

.btn-modify:hover {
  background: #6c757d;
  color: white;
}

.btn-modify:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.order-info-content {
  padding: 20px;
  background: white;
  transition: all 0.3s ease;
}

.order-info-content.locked {
  background: #f8f9fa;
  opacity: 0.8;
}

.order-info-content.locked .form-input:disabled,
.order-info-content.locked .form-select:disabled,
.order-info-content.locked .form-textarea:disabled {
  background: #e9ecef;
  color: #6c757d;
  cursor: not-allowed;
}

.lock-notice {
  margin-top: 16px;
  padding: 12px 24px;
  background: #fff3cd;
  border: 1px solid #ffeaa7;
  border-radius: 8px;
}

.notice-content {
  display: flex;
  align-items: center;
  gap: 8px;
}

.notice-icon {
  font-size: 16px;
  flex-shrink: 0;
}

.notice-text {
  font-size: 13px;
  color: #856404;
  line-height: 1.4;
}

/* 付款紀錄readonly樣式 */
.readonly-field {
  background: #f8f9fa !important;
  color: #6c757d !important;
  cursor: not-allowed !important;
  border-color: #dee2e6 !important;
}

.readonly-field::placeholder {
  color: #adb5bd !important;
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

.payment-status-display {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.status-note {
  color: #6c757d;
  font-size: 12px;
  font-style: italic;
}

@media (max-width: 768px) {
  .route-management { padding:10px; }
  .page-header { flex-direction:column; align-items:flex-start; gap:15px; }
  .filters-section { flex-direction:column; align-items:stretch; }
  .filter-controls { flex-direction:column; align-items:stretch; }
  .form-row { flex-direction:column; gap:12px; }
  .form-actions { flex-direction:column; }
  .pagination-container { flex-direction:column; gap:15px; text-align:center; }
  .admin-table { font-size:12px; }
  .admin-table th, .admin-table td { padding:8px 6px; }
}
</style>
