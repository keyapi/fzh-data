const { createApp, ref, onMounted, computed } = Vue

createApp({
  setup() {
    const keys = ref([])
    const accounts = ref({})
    const user = ref({ role: 'user', name: '' })
    const error = ref('')
    const showCreate = ref(false)
    const createdKey = ref('')
    const copied = ref(false)
    const form = ref({ name: '', account: '', rate_limit_rps: 1.0 })

    const isAdmin = computed(() => user.value.role === 'admin')
    const usageExample = computed(() => {
      if (!createdKey.value || !form.value.account) return ''
      return `curl -X POST https://api.vilavi.cn/sellfox/v1/${form.value.account}/api/shop/pageList.json \\
  -H "Authorization: Bearer ${createdKey.value}" \\
  -H "Content-Type: application/json" \\
  -d '{"pageSize":10}'`
    })

    async function loadKeys() {
      try {
        const resp = await fetch('api/keys')
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
        const data = await resp.json()
        keys.value = data.keys
        error.value = ''
      } catch (e) { error.value = '加载失败: ' + e.message }
    }

    async function loadUser() {
      try {
        const resp = await fetch('api/me')
        if (resp.ok) user.value = await resp.json()
      } catch (e) { user.value = { role: 'user', name: '' } }
    }

    async function loadAccounts() {
      try {
        const resp = await fetch('api/accounts')
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
        accounts.value = await resp.json()
        const ks = Object.keys(accounts.value)
        if (ks.length && !form.value.account) {
          form.value.account = ks[0]
          form.value.rate_limit_rps = accounts.value[ks[0]].rate_limit_rps
        }
      } catch (e) { error.value = '加载失败: ' + e.message }
    }

    function onAccountChange() {
      const acc = accounts.value[form.value.account]
      if (acc) form.value.rate_limit_rps = acc.rate_limit_rps
    }

    async function createKey() {
      try {
        const resp = await fetch('api/keys', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(form.value),
        })
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
        const data = await resp.json()
        createdKey.value = data.key
        form.value.name = ''
        await loadKeys()
      } catch (e) { error.value = '创建失败: ' + e.message }
    }

    async function toggleKey(k) {
      try {
        const resp = await fetch('api/keys/' + k.id + '/toggle', { method: 'POST' })
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
        await loadKeys()
      } catch (e) { error.value = '操作失败: ' + e.message }
    }

    async function deleteKey(k) {
      if (!confirm('确认删除 Key "' + k.name + '"？')) return
      try {
        const resp = await fetch('api/keys/' + k.id, { method: 'DELETE' })
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
        await loadKeys()
      } catch (e) { error.value = '删除失败: ' + e.message }
    }

    async function copyExistingKey(k) {
      try {
        const resp = await fetch('api/keys/' + k.id + '/reveal', { method: 'POST' })
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
        const data = await resp.json()
        if (!data.key) throw new Error('empty response')
        try {
          await navigator.clipboard.writeText(data.key)
        } catch {
          const ta = document.createElement('textarea')
          ta.value = data.key; ta.style.position = 'fixed'; ta.style.left = '-9999px'
          document.body.appendChild(ta); ta.select()
          document.execCommand('copy'); document.body.removeChild(ta)
        }
        alert('已复制到剪贴板！')
      } catch (e) {
        error.value = '无法复制此 Key（可能是旧版 Key 不支持）。请删除后重新创建。'
      }
    }

    async function copyCreatedKey() {
      try {
        await navigator.clipboard.writeText(createdKey.value)
        copied.value = true
        setTimeout(() => { copied.value = false }, 2000)
      } catch {
        const ta = document.createElement('textarea')
        ta.value = createdKey.value; ta.style.position = 'fixed'; ta.style.left = '-9999px'
        document.body.appendChild(ta); ta.select()
        document.execCommand('copy'); document.body.removeChild(ta)
        copied.value = true
        setTimeout(() => { copied.value = false }, 2000)
      }
    }

    function resetForm() { createdKey.value = ''; copied.value = false }

    onMounted(() => { loadUser(); loadKeys(); loadAccounts() })

    return {
      keys, accounts, user, isAdmin, error, showCreate, createdKey, copied, form,
      usageExample, loadKeys, createKey, toggleKey, deleteKey,
      copyExistingKey, copyCreatedKey, resetForm, onAccountChange,
    }
  },
}).mount('#app')
