<template>
  <el-config-provider :locale="zhCn">
    <div class="app-nav">
      <el-menu mode="horizontal" :default-active="activeTab" @select="activeTab = $event">
        <el-menu-item index="chat">
          <el-icon><ChatDotRound /></el-icon>
          智能对话
        </el-menu-item>
        <el-menu-item index="aws">
          <el-icon><Odometer /></el-icon>
          AWS 巡检
        </el-menu-item>
        <el-menu-item index="huawei-check">
          <el-icon><DocumentChecked /></el-icon>
          华为云巡检
        </el-menu-item>
      </el-menu>
    </div>
    <ChatView v-if="activeTab === 'chat'" />
    <Dashboard v-else-if="activeTab === 'aws'" />
    <HuaweiCheck v-else-if="activeTab === 'huawei-check'" />
  </el-config-provider>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import zhCn from 'element-plus/es/locale/lang/zh-cn'
import ChatView from './views/ChatView.vue'
import Dashboard from './views/Dashboard.vue'
import HuaweiCheck from './views/HuaweiCheck.vue'

const activeTab = ref('chat')
</script>

<style>
body {
  margin: 0;
  background: #f5f7fa;
}
.app-nav {
  background: #fff;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.08);
}
.app-nav .el-menu {
  max-width: 1600px;
  margin: 0 auto;
}
</style>
