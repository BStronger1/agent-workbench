<script setup lang="ts">
import { onMounted, ref } from "vue";
interface Settings {
  enabled: boolean;
  baseUrl: string;
  model: string;
  hasKey: boolean;
  keyMask: string;
  inputPrice: number;
  outputPrice: number;
  allowedHosts: string[];
}
const props = defineProps<{
  request: (path: string, method?: string, body?: unknown) => Promise<any>;
}>();
const emit = defineEmits<{ saved: [] }>();
const saved = ref<Settings | null>(null);
const form = ref({
  enabled: true,
  baseUrl: "https://api.deepseek.com/v1",
  model: "deepseek-chat",
  apiKey: "",
  inputPrice: 0,
  outputPrice: 0,
});
const busy = ref(false),
  error = ref(""),
  message = ref("");
const insecure =
  location.protocol !== "https:" &&
  !["localhost", "127.0.0.1", "[::1]"].includes(location.hostname);
async function load() {
  saved.value = await props.request("/provider");
  const s = saved.value!;
  form.value = {
    enabled: s.hasKey ? s.enabled : true,
    baseUrl: s.baseUrl,
    model: s.model,
    apiKey: "",
    inputPrice: s.inputPrice,
    outputPrice: s.outputPrice,
  };
}
async function action(fn: () => Promise<void>) {
  busy.value = true;
  error.value = "";
  message.value = "";
  try {
    await fn();
  } catch (e) {
    error.value = e instanceof Error ? e.message : "操作失败";
  } finally {
    busy.value = false;
  }
}
async function save() {
  await action(async () => {
    await props.request("/provider", "POST", form.value);
    form.value.apiKey = "";
    await load();
    emit("saved");
    message.value = saved.value?.enabled
      ? "配置已保存，后续生成将使用你的模型。"
      : "配置已保存，个人模型暂未启用。";
  });
}
async function test() {
  await action(async () => {
    const result = await props.request("/provider/test", "POST", {});
    message.value = result.message;
  });
}
async function clear() {
  await action(async () => {
    await props.request("/provider", "DELETE");
    await load();
    emit("saved");
    message.value = "模型配置和已保存的 Key 已清除。";
  });
}
onMounted(() => action(load));
</script>

<template>
  <section class="panel padded model-settings">
    <div class="panel-title">
      <div>
        <h3>连接你自己的大模型</h3>
        <p class="muted">
          支持 Chat Completions
          兼容接口。保存配置不会调用模型，启用后供当前项目空间使用。
        </p>
      </div>
      <span class="pill" :class="{ success: saved?.enabled }">{{
        saved?.enabled ? "已启用" : "未启用"
      }}</span>
    </div>
    <p v-if="insecure" class="notice">
      当前页面使用 HTTP，请在可信内网或 SSH 隧道中填写 Key；公网访问请使用
      HTTPS。
    </p>
    <div v-if="error" class="error" role="alert">{{ error }}</div>
    <p v-if="message" class="settings-success" role="status">{{ message }}</p>
    <form @submit.prevent="save">
      <label for="provider-base">接口地址（Base URL）</label>
      <input
        id="provider-base"
        v-model="form.baseUrl"
        type="url"
        required
        maxlength="300"
        placeholder="https://api.deepseek.com/v1"
        spellcheck="false"
      />
      <small class="muted"
        >填写服务商提供的 API 基础地址，无需添加 /chat/completions。</small
      >
      <label for="provider-model">模型名称</label>
      <input
        id="provider-model"
        v-model="form.model"
        required
        maxlength="150"
        placeholder="例如 deepseek-chat、qwen-plus，按服务商实际名称填写"
        spellcheck="false"
      />
      <label for="provider-key"
        >API Key
        <span v-if="saved?.hasKey" class="saved-key"
          >已保存 {{ saved.keyMask }}</span
        ></label
      >
      <input
        id="provider-key"
        v-model="form.apiKey"
        type="password"
        :required="!saved?.hasKey"
        maxlength="4096"
        autocomplete="new-password"
        :placeholder="
          saved?.hasKey
            ? '留空保留现有 Key；输入新 Key 可替换'
            : '粘贴你的 API Key'
        "
        spellcheck="false"
      />
      <p class="muted">
        Key
        在服务器加密保存，不回传完整值，也不写入项目报告。配置属于当前浏览器空间，清除
        Cookie 后无法访问原配置。
      </p>
      <details>
        <summary>费用估算（选填）</summary>
        <div class="form-row">
          <label
            >输入价格 / 百万 Token<input
              v-model.number="form.inputPrice"
              type="number"
              min="0"
              max="100000"
              step="any" /></label
          ><label
            >输出价格 / 百万 Token<input
              v-model.number="form.outputPrice"
              type="number"
              min="0"
              max="100000"
              step="any"
          /></label>
        </div>
        <p class="muted">
          使用同一计费币种；填 0 表示不估算费用。实际费用以服务商账单为准。
        </p>
      </details>
      <label class="check"
        ><input
          v-model="form.enabled"
          type="checkbox"
        />启用我的模型用于生成</label
      >
      <div class="settings-actions">
        <button class="primary" :disabled="busy" type="submit">
          保存模型配置</button
        ><button
          class="secondary"
          :disabled="busy || !saved?.enabled"
          type="button"
          @click="test"
        >
          测试已保存配置（少量 Token）</button
        ><button
          class="text-button"
          :disabled="busy || !saved?.hasKey"
          type="button"
          @click="clear"
        >
          清除模型配置
        </button>
      </div>
    </form>
    <details>
      <summary>支持的接口域名与示例</summary>
      <p class="muted">
        DeepSeek：https://api.deepseek.com/v1<br />阿里云百炼：https://dashscope.aliyuncs.com/compatible-mode/v1<br />SiliconFlow：https://api.siliconflow.cn/v1<br />OpenAI：https://api.openai.com/v1
      </p>
      <p class="muted">{{ saved?.allowedHosts.join(" · ") }}</p>
      <p class="muted">
        使用其他兼容服务时，部署者可通过 PROVIDER_ALLOWED_HOSTS 扩展域名列表。
      </p>
    </details>
  </section>
</template>
