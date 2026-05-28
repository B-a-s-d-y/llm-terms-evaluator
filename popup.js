const privacyBtn = document.getElementById('privacy-btn');
const tosBtn = document.getElementById('tos-btn');
const backBtn = document.getElementById('back-btn');
const btnContainer = document.getElementById('btn-container');
const progressUi = document.getElementById('progress-ui');
const statusDiv = document.getElementById('status');

let pollingInterval = null;
let currentExtractedText = '';
let currentActionType = '';
let currentTitle = '';
let currentUrl = '';

privacyBtn.addEventListener('click', () => startExtraction('privacy'));
tosBtn.addEventListener('click', () => startExtraction('tos'));
backBtn.addEventListener('click', resetView);

function resetView() {
  btnContainer.style.display = 'block';
  progressUi.style.display = 'none';
  backBtn.style.display = 'none';
  statusDiv.innerHTML = '';
}

function updateProgressUI(current) {
  const pt = document.getElementById('progress-text');
  const messages = [
    "解析网页中，即将进行第 1 轮深度分析...",
    "等待中...正在交叉对比第 2 轮评估结果...",
    "最后校验中...启动第 3 轮...",
    "太棒了！分析已完成，正在生成报告..."
  ];
  pt.textContent = messages[Math.min(current, 3)];

  for(let i=1; i<=3; i++) {
    const dot = document.getElementById('dot-' + i);
    dot.className = 'dot'; // 清空附加 class
    if (i <= current) {
      dot.classList.add('completed');
    } else if (i === current + 1) {
      dot.classList.add('running');
    }
  }
}

async function startPolling() {
  pollingInterval = setInterval(async () => {
    try {
      const res = await fetch('http://localhost:8000/progress');
      if (res.ok) {
        const data = await res.json();
        updateProgressUI(data.progress || 0);
      }
    } catch(e) {}
  }, 1000);
}

function stopPolling() {
  if(pollingInterval) {
    clearInterval(pollingInterval);
    pollingInterval = null;
  }
}

async function startExtraction(actionType) {
  btnContainer.style.display = 'none';
  progressUi.style.display = 'flex';
  statusDiv.innerHTML = '';
  
  // 初始为等待第一轮状态
  updateProgressUI(0);

  try {
    let [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    
    chrome.scripting.executeScript({
      target: { tabId: tab.id },
      func: () => document.body.innerText
    }, async (results) => {
      if (chrome.runtime.lastError) {
        statusDiv.innerHTML = '<div style="color:red; text-align:center;">提取失败: ' + chrome.runtime.lastError.message + '</div>';
        progressUi.style.display = 'none';
        backBtn.style.display = 'block';
        return;
      }
      
      const text = results[0]?.result || '';
      if (!text.trim()) {
        statusDiv.innerHTML = '<div style="color:red; text-align:center;">未能提取到有效网页内容</div>';
        progressUi.style.display = 'none';
        backBtn.style.display = 'block';
        return;
      }

      currentExtractedText = text;
      currentActionType = actionType;
      currentTitle = tab.title || "未知页面";
      currentUrl = tab.url || "未知URL";

      startPolling();
      await sendToPython(text, actionType);
    });

  } catch (error) {
    statusDiv.innerHTML = '<div style="color:red; text-align:center;">错误: ' + error.message + '</div>';
    progressUi.style.display = 'none';
    backBtn.style.display = 'block';
  }
}

function createRadarChartSVG(dimData) {
  const size = 340;
  const center = size / 2;
  const radius = size / 2 - 100;
  const sides = dimData.length;
  if(sides < 3) return '';
  const angleStep = (Math.PI * 2) / sides;
  
  let svg = '<div style="text-align:center; margin: 15px 0;"><svg width="100%" height="auto" viewBox="0 0 340 340" style="max-width:340px;" xmlns="http://www.w3.org/2000/svg">';
  
  // Background polygons
  for (let level = 1; level <= 5; level++) {
    const r = radius * (level / 5);
    let points = [];
    for (let i = 0; i < sides; i++) {
        const a = (i * angleStep) - Math.PI/2;
        points.push((center + r * Math.cos(a)) + ',' + (center + r * Math.sin(a)));
    }
    svg += '<polygon points="' + points.join(' ') + '" fill="none" stroke="#ecf0f1" stroke-width="1"/>';
  }
  
  // Axis lines & labels & data points calculation
  let dataPoints = [];
  dimData.forEach((d, i) => {
    const a = (i * angleStep) - Math.PI/2;
    const x = center + radius * Math.cos(a);
    const y = center + radius * Math.sin(a);
    svg += '<line x1="' + center + '" y1="' + center + '" x2="' + x + '" y2="' + y + '" stroke="#ecf0f1" stroke-width="1"/>';
    
    // Label positioning
    const lx = center + (radius + 20) * Math.cos(a);
    const ly = center + (radius + 20) * Math.sin(a);
    let anchor = "middle";
    if(lx < center - 10) anchor = "end";
    if(lx > center + 10) anchor = "start";
    
    const pct = d.max ? d.score / d.max : 0;
    const dx = center + (radius * pct) * Math.cos(a);
    const dy = center + (radius * pct) * Math.sin(a);
    dataPoints.push(dx + ',' + dy);
    
    // Calculate display score text length to avoid breaking label layout too much
    let nameText = d.name;
    // Strip numbering like "1. " from name if exists
    nameText = nameText.replace(/^\d+\.\s*/, '');
    
    svg += '<text x="' + lx + '" y="' + ly + '" text-anchor="' + anchor + '" font-size="11" fill="#34495e" font-weight="bold" font-family="sans-serif">' + nameText + '</text>';
    svg += '<text x="' + lx + '" y="' + (ly+14) + '" text-anchor="' + anchor + '" font-size="10" fill="#7f8c8d" font-family="sans-serif">' + d.score + '/' + d.max + '</text>';
  });
  
  // Data polygon fill
  svg += '<polygon points="' + dataPoints.join(' ') + '" fill="rgba(79, 172, 254, 0.3)" stroke="#00f2fe" stroke-width="2"/>';
  // Add dots on edges
  dataPoints.forEach(p => {
      let coords = p.split(',');
      svg += '<circle cx="' + coords[0] + '" cy="' + coords[1] + '" r="4" fill="#4facfe" stroke="#fff" stroke-width="1.5"/>';
  });
  
  svg += '</svg></div>';
  return svg;
}

window.forceAnalyze = async function() {
  statusDiv.innerHTML = '';
  progressUi.style.display = 'flex';
  backBtn.style.display = 'none';
  updateProgressUI(0);
  startPolling();
  await sendToPython(currentExtractedText, currentActionType, true);
};

async function sendToPython(text, action, isForce = false) {
  try {
    const response = await fetch('http://localhost:8000/', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ 
        text: text, 
        action: action, 
        force: isForce,
        title: currentTitle,
        url: currentUrl
      })
    });
    
    stopPolling();
    updateProgressUI(3);
    
    // 短暂延迟隐藏动画增强体验
    setTimeout(async () => {
      progressUi.style.display = 'none';
      
      if (response.ok) {
        const data = await response.json();
        
        let html = '';
        
        if(data.computed && data.computed.dimension_scores) {
          const c = data.computed;
          
          const textLength = currentExtractedText.length;
          const kLength = Math.round(textLength / 1000);
          const minTime = Math.round(textLength / 300);
          const maxTime = Math.round(textLength / 250);
          
          html += '<div style="text-align: right; font-size: 11px; color: #95a5a6; margin-bottom: 8px;">';
          html += '(全文字数约' + kLength + ' k，完整阅读预计用时' + minTime + '~' + maxTime + '分钟)';
          html += '</div>';

          html += '<div class="final-score-box">';
          html += '<p>综合安全信任评分</p>';
          html += '<span>' + c.final_score + ' / ' + c.max_total + ' (' + c.percent + '%)</span>';
          html += '</div>';

          const dimData = Object.values(c.dimension_scores);
          if(dimData && dimData.length >= 3) {
            html += '<div class="section-title">📊 多维能力雷达图</div>';
            html += createRadarChartSVG(dimData);
          }
        }
        
        if(data.formatted_scores && data.formatted_scores.length > 0) {
          html += '<div class="section-title">📄 评估细则</div>';
          data.formatted_scores.forEach(dim => {
            html += '<div style="margin-top: 15px; margin-bottom: 5px; font-weight: bold; color: #2980b9;">' + dim.dimension.replace(/^\d+\.\s*/, '') + '</div>';
            dim.items.forEach(item => {
              html += '<div class="score-item">';
              html += '<div><span class="sc-title">' + item.indicator + '</span><span class="sc-val">' + (item.score !== undefined ? item.score : 0) + '/' + (item.max !== undefined ? item.max : 2) + ' 分</span></div>';
              html += '<span class="sc-comment">' + item.comment + '</span>';
              html += '</div>';
            });
          });
        }
        
        if(data.special_items && data.special_items.length > 0) {
          html += '<div class="section-title">⚠️ 数据过度采集预警</div>';
          data.special_items.forEach(item => {
            if(item.hit) {
              html += '<div class="deduct-item"><span>❌ ' + item.desc + '</span> <strong>- ' + item.pen + ' 分</strong></div>';
            } else {
              html += '<div class="no-deduct-item"><span>✅ ' + item.desc + '</span> <span style="font-size: 12px; color: #7f8c8d; padding-top:2px;">无风险</span></div>';
            }
          });
        }
        
        statusDiv.innerHTML = html;
      } else {
        let errText = await response.text();
        try {
          const errObj = JSON.parse(errText);
          if (errObj.error) errText = errObj.error;
        } catch (e) {}
        // Replace newlines with <br> for better rendering
        errText = errText.replace(/\n/g, '<br>');
        
        if (errText.includes('[PRECHECK_FAILED]')) {
          errText = errText.replace('[PRECHECK_FAILED] ', '');
          let targetName = currentActionType === 'tos' ? '用户服务协议' : '隐私政策';
          
          let alertHtml = '<div style="color:#e74c3c; background:#fadbd8; padding:15px; border-radius:8px; text-align:center; font-weight:bold; margin-bottom: 10px; box-shadow: 0 2px 5px rgba(0,0,0,0.1);">';
          alertHtml += '🛑 预检查未通过:<br><br><span style="font-weight:normal; font-size:13px;">';
          alertHtml += errText + '</span>';
          alertHtml += '</div>';
          
          alertHtml += '<div style="font-size: 13px; color: #555; text-align: left; padding: 10px; background: #fff; border: 1px solid #ddd; border-radius: 6px; margin-bottom: 10px;">';
          alertHtml += '💡 <b>提示：</b>由于网页排版或内容特征不明显，模型判定这不是一份典型的【' + targetName + '】。<br><br>若您确认这就是【' + targetName + '】，请点击下方按钮跳过拦截，继续深度分析。';
          alertHtml += '</div>';
          
          alertHtml += '<button id="force-analyze-btn" class="btn" style="background:#e67e22; margin-bottom: 15px;">⚠️ 强制执行深度检测</button>';
          
          statusDiv.innerHTML = alertHtml;
          // 绑定动态按钮事件（避免使用内联 onclick，MV3 要求）
          try {
            const btn = document.getElementById('force-analyze-btn');
            if (btn) btn.addEventListener('click', window.forceAnalyze);
          } catch (e) {}
        } else {
          statusDiv.innerHTML = '<div style="color:#e74c3c; background:#fadbd8; padding:15px; border-radius:8px; text-align:center; font-weight:bold; box-shadow: 0 2px 5px rgba(0,0,0,0.1);">🛑 服务器拦截:<br><br>' + errText + '</div>';
        }
      }
      
      backBtn.style.display = 'block';
    }, 600); // 留600ms展示全绿动画
    
  } catch (error) {
    stopPolling();
    progressUi.style.display = 'none';
    statusDiv.innerHTML = '<div style="color:red; text-align:center;">网络错误：无法连接到本地 Python 模型服务<br><br>' + error.message + '</div>';
    backBtn.style.display = 'block';
  }
}
