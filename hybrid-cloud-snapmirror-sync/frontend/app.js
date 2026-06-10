/**
 * SnapMirror One-Click Sync — フロントエンドロジック
 *
 * ポーリングベースの状態管理で、リアルタイムに同期進捗を表示する。
 */

(function () {
  "use strict";

  // --- DOM 要素 ---
  const syncButton = document.getElementById("sync-button");
  const buttonIcon = document.getElementById("button-icon");
  const buttonText = document.getElementById("button-text");
  const statusDot = document.getElementById("status-dot");
  const statusText = document.getElementById("status-text");
  const statusDetail = document.getElementById("status-detail");
  const progressSection = document.getElementById("progress-section");
  const progressBar = document.getElementById("progress-bar");
  const transferInfo = document.getElementById("transfer-info");
  const bytesTransferred = document.getElementById("bytes-transferred");
  const startTime = document.getElementById("start-time");
  const completionMessage = document.getElementById("completion-message");
  const errorMessage = document.getElementById("error-message");
  const errorText = document.getElementById("error-text");
  const retryButton = document.getElementById("retry-button");
  const warningBanner = document.getElementById("warning-banner");
  const warningText = document.getElementById("warning-text");
  const demoBadge = document.getElementById("demo-badge");

  const steps = [
    document.getElementById("step-1"),
    document.getElementById("step-2"),
    document.getElementById("step-3"),
  ];

  // --- 状態 ---
  let pollingInterval = null;
  let currentPhase = "ready";

  // --- 初期化 ---
  async function init() {
    syncButton.addEventListener("click", handleSyncClick);
    retryButton.addEventListener("click", handleRetryClick);

    // 起動時ヘルスチェック
    await checkHealth();

    // 初回ステータス取得
    await fetchStatus();

    // ポーリング開始（3秒間隔）
    startPolling(3000);
  }

  // --- ヘルスチェック ---
  async function checkHealth() {
    try {
      const response = await fetch("/api/health");
      if (!response.ok) return;
      const data = await response.json();

      // デモモード表示
      if (data.demo_mode) {
        demoBadge.style.display = "block";
      }

      if (!data.snapmirror_healthy && data.snapmirror_uuid_configured && !data.demo_mode) {
        warningBanner.style.display = "block";
        warningText.textContent =
          "SnapMirror 関係に問題があります (state: " +
          data.snapmirror_state +
          ")";
      } else {
        warningBanner.style.display = "none";
      }
    } catch (e) {
      // ignore
    }
  }

  // --- API 通信 ---
  async function fetchStatus() {
    try {
      const response = await fetch("/api/status");
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const data = await response.json();
      updateUI(data.state);
    } catch (error) {
      console.error("Status fetch error:", error);
      showConnectionError();
    }
  }

  async function triggerSync() {
    try {
      const response = await fetch("/api/sync", { method: "POST" });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const data = await response.json();

      if (data.success) {
        // ポーリング頻度を上げる
        startPolling(1500);
      } else {
        updateUI(data.state);
      }
    } catch (error) {
      console.error("Sync trigger error:", error);
      showError("サーバーに接続できません。ネットワークを確認してください。");
    }
  }

  // --- イベントハンドラ ---
  function handleSyncClick() {
    // 即座にボタンを無効化（二重クリック防止）
    syncButton.disabled = true;
    syncButton.classList.add("syncing");
    buttonIcon.textContent = "⏳";
    buttonText.textContent = "開始中...";

    triggerSync();
  }

  function handleRetryClick() {
    hideAllMessages();
    handleSyncClick();
  }

  // --- UI 更新 ---
  function updateUI(state) {
    if (!state) return;

    currentPhase = state.phase;

    switch (state.phase) {
      case "ready":
        showReady(state);
        break;
      case "starting":
        showStarting(state);
        break;
      case "syncing":
        showSyncing(state);
        break;
      case "completing":
        showCompleting(state);
        break;
      case "done":
        showDone(state);
        break;
      case "error":
        showError(state.error_message || state.message);
        break;
    }
  }

  function showReady(state) {
    // ボタン有効化
    syncButton.disabled = false;
    syncButton.classList.remove("syncing");
    buttonIcon.textContent = "▶";
    buttonText.textContent = "同期開始";

    // ステータス
    statusDot.className = "status-dot ready";
    statusText.textContent = "同期可能";
    statusDetail.textContent = state.message || "";

    // 進捗非表示
    hideAllMessages();
    progressSection.style.display = "none";
    transferInfo.style.display = "none";

    // ポーリング頻度を戻す
    startPolling(3000);
  }

  function showStarting(state) {
    syncButton.disabled = true;
    syncButton.classList.add("syncing");
    buttonIcon.textContent = "⏳";
    buttonText.textContent = "開始中...";

    statusDot.className = "status-dot syncing";
    statusText.textContent = "同期開始中";
    statusDetail.textContent = "SnapMirror 更新を準備しています...";

    hideAllMessages();
    progressSection.style.display = "block";
    progressBar.style.width = "10%";
    progressBar.classList.remove("indeterminate");
    setActiveStep(0);
  }

  function showSyncing(state) {
    syncButton.disabled = true;
    syncButton.classList.add("syncing");
    buttonIcon.textContent = "🔄";
    buttonText.textContent = "同期中...";

    statusDot.className = "status-dot syncing";
    statusText.textContent = "データ同期中";
    statusDetail.textContent = state.message || "転送中...";

    hideAllMessages();
    progressSection.style.display = "block";
    progressBar.classList.add("indeterminate");
    setActiveStep(1);

    // 転送情報を表示
    if (state.bytes_transferred > 0 || state.started_at) {
      transferInfo.style.display = "block";
      if (state.bytes_transferred > 0) {
        const mb = (state.bytes_transferred / (1024 * 1024)).toFixed(1);
        bytesTransferred.textContent = `${mb} MB`;
      }
      if (state.started_at) {
        const time = new Date(state.started_at).toLocaleTimeString("ja-JP");
        startTime.textContent = time;
      }
    }
  }

  function showCompleting(state) {
    syncButton.disabled = true;
    buttonIcon.textContent = "✓";
    buttonText.textContent = "完了処理中";

    statusDot.className = "status-dot syncing";
    statusText.textContent = "完了処理中";
    statusDetail.textContent = "最終確認中...";

    progressBar.classList.remove("indeterminate");
    progressBar.style.width = "90%";
    setActiveStep(2);
  }

  function showDone(state) {
    syncButton.disabled = false;
    syncButton.classList.remove("syncing");
    buttonIcon.textContent = "▶";
    buttonText.textContent = "再同期";

    statusDot.className = "status-dot done";
    statusText.textContent = "同期完了";

    if (state.completed_at) {
      const time = new Date(state.completed_at).toLocaleTimeString("ja-JP");
      statusDetail.textContent = `完了時刻: ${time}`;
    }

    // 進捗バーを100%に
    progressSection.style.display = "block";
    progressBar.classList.remove("indeterminate");
    progressBar.style.width = "100%";
    setActiveStep(3);

    // 完了メッセージ
    hideAllMessages();
    completionMessage.style.display = "block";

    // ポーリング頻度を戻す
    startPolling(3000);

    // 10秒後に完了メッセージを非表示にして ready に戻す
    setTimeout(() => {
      if (currentPhase === "done") {
        completionMessage.style.display = "none";
      }
    }, 10000);
  }

  function showError(message) {
    syncButton.disabled = false;
    syncButton.classList.remove("syncing");
    buttonIcon.textContent = "▶";
    buttonText.textContent = "リトライ";

    statusDot.className = "status-dot error";
    statusText.textContent = "エラー";
    statusDetail.textContent = "";

    hideAllMessages();
    errorMessage.style.display = "block";
    errorText.textContent = message || "エラーが発生しました";

    progressSection.style.display = "none";
    transferInfo.style.display = "none";

    // ポーリング頻度を戻す
    startPolling(3000);
  }

  function showConnectionError() {
    statusDot.className = "status-dot error";
    statusText.textContent = "接続エラー";
    statusDetail.textContent = "サーバーに接続できません";
    syncButton.disabled = true;
  }

  // --- ユーティリティ ---
  function hideAllMessages() {
    completionMessage.style.display = "none";
    errorMessage.style.display = "none";
  }

  function setActiveStep(activeIndex) {
    steps.forEach((step, i) => {
      step.classList.remove("active", "completed");
      if (i < activeIndex) {
        step.classList.add("completed");
      } else if (i === activeIndex) {
        step.classList.add("active");
      }
    });
  }

  function startPolling(intervalMs) {
    if (pollingInterval) {
      clearInterval(pollingInterval);
    }
    pollingInterval = setInterval(fetchStatus, intervalMs);
  }

  // --- 起動 ---
  document.addEventListener("DOMContentLoaded", init);

  // タブ非アクティブ時はポーリングを減速
  document.addEventListener("visibilitychange", function () {
    if (document.visibilityState === "hidden") {
      startPolling(30000); // 30秒間隔に減速
    } else {
      // アクティブに戻ったら即座にステータス取得 + 通常間隔に復帰
      fetchStatus();
      startPolling(currentPhase === "syncing" ? 1500 : 3000);
    }
  });
})();
