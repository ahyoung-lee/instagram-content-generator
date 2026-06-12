// Global State for current generation
let currentPostData = {
    image_paths: [],
    caption: '',
    date_str: '',
    zip_url: ''
};

// --- Background Image Rotation System (3 Hours / 10,800,000ms) ---
const BG_ROTATION_INTERVAL = 10800000; // 3 hours
const bgImages = ['img/bgimg1.jpg', 'img/bgimg2.jpg', 'img/bgimg3.jpg', 'img/tai00020004619.jpg'];
let activeBgImages = [];
let currentBgIndex = 0;

async function checkFileExists(url) {
    try {
        const response = await fetch(url, { method: 'HEAD' });
        return response.ok;
    } catch (e) {
        return false;
    }
}

async function initializeBackgroundRotation() {
    // Scan which background images actually exist
    for (const imgPath of bgImages) {
        const exists = await checkFileExists(imgPath);
        if (exists) {
            activeBgImages.push(imgPath);
        }
    }

    // Fallback if no images are found
    if (activeBgImages.length === 0) {
        activeBgImages.push('img/bgimg1.jpg');
    }

    console.log("Discovered active background images:", activeBgImages);
    
    // Set first background
    document.body.style.setProperty('--bg-image', `url('${activeBgImages[0]}')`);

    // Start interval
    setInterval(rotateBackground, BG_ROTATION_INTERVAL);
}

function rotateBackground() {
    if (activeBgImages.length <= 1) return;
    currentBgIndex = (currentBgIndex + 1) % activeBgImages.length;
    const nextImage = activeBgImages[currentBgIndex];
    console.log(`Rotating background to: ${nextImage}`);
    document.body.style.setProperty('--bg-image', `url('${nextImage}')`);
}

// --- API Orchestration & UI Control ---

const urlInput = document.getElementById('url-input');
const generateBtn = document.getElementById('generate-btn');
const resultsSection = document.getElementById('results-section');
const loadingOverlay = document.getElementById('loading-overlay');
const dateBadge = document.getElementById('date-badge');
const slidesGrid = document.getElementById('slides-grid');
const captionText = document.getElementById('caption-text');
const copyCaptionBtn = document.getElementById('copy-caption-btn');
const publishBtn = document.getElementById('publish-btn');
const statusBox = document.getElementById('status-box');
const statusLog = document.getElementById('status-log');
const fallbackActions = document.getElementById('fallback-actions');
const downloadZipBtn = document.getElementById('download-zip-btn');

// 1. Generate Content
generateBtn.addEventListener('click', async () => {
    const url = urlInput.value.strip ? urlInput.value.strip() : urlInput.value.trim();
    
    // Show Loading Overlay
    loadingOverlay.classList.remove('hidden');
    resultsSection.classList.add('hidden');
    statusBox.classList.add('hidden');
    fallbackActions.classList.add('hidden');

    try {
        const response = await fetch('/api/generate', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ url: url || null })
        });

        if (!response.ok) {
            throw new Error(`서버 에러 발생 (상태 코드: ${response.status})`);
        }

        const data = await response.json();
        
        if (data.success) {
            // Update Global State
            currentPostData.image_paths = data.absolute_paths;
            currentPostData.caption = data.plan.final_caption;
            currentPostData.date_str = data.date_str;
            
            // Format ZIP URL (assuming zip is created under save/YYYY-MM-DD/)
            // We'll update the download button link with this relative path
            
            // Populate UI Elements
            dateBadge.textContent = data.date_str;
            captionText.value = data.plan.final_caption;
            
            // Render Slide Images Preview
            slidesGrid.innerHTML = '';
            data.image_urls.forEach((url, index) => {
                const wrapper = document.createElement('div');
                wrapper.className = 'slide-preview-wrapper';
                wrapper.style.cursor = 'pointer';
                
                const img = document.createElement('img');
                img.src = url;
                img.alt = `Slide ${index + 1}`;
                
                const badge = document.createElement('div');
                badge.className = 'slide-number';
                badge.textContent = index + 1;
                
                wrapper.appendChild(img);
                wrapper.appendChild(badge);
                
                // Click to open preview modal
                wrapper.addEventListener('click', () => {
                    const modal = document.getElementById('image-modal');
                    const modalImg = document.getElementById('modal-img');
                    modal.classList.remove('hidden');
                    modalImg.src = url;
                });
                
                slidesGrid.appendChild(wrapper);
            });
            
            // Show Results
            resultsSection.classList.remove('hidden');
        } else {
            alert(`콘텐츠 생성 실패: ${data.error || '알 수 없는 오류'}`);
        }
    } catch (error) {
        console.error(error);
        alert(`요청 처리 중 오류가 발생했습니다: ${error.message}`);
    } finally {
        // Hide Loading Overlay
        loadingOverlay.classList.add('hidden');
    }
});

// 2. Copy Caption to Clipboard
copyCaptionBtn.addEventListener('click', () => {
    captionText.select();
    captionText.setSelectionRange(0, 99999); // For mobile devices
    
    navigator.clipboard.writeText(captionText.value)
        .then(() => {
            const originalText = copyCaptionBtn.textContent;
            copyCaptionBtn.textContent = '✅ 복사 완료!';
            copyCaptionBtn.style.background = 'rgba(16, 185, 129, 0.2)';
            copyCaptionBtn.style.color = '#10b981';
            
            setTimeout(() => {
                copyCaptionBtn.textContent = originalText;
                copyCaptionBtn.style.background = '';
                copyCaptionBtn.style.color = '';
            }, 2000);
        })
        .catch(err => {
            console.error('클립보드 복사 실패:', err);
            alert('클립보드 복사 중 오류가 발생했습니다. 직접 선택하여 복사해 주세요.');
        });
});

// 3. Publish to Instagram
publishBtn.addEventListener('click', async () => {
    // Disable button to prevent double submission
    publishBtn.disabled = true;
    publishBtn.textContent = '⏳ 발행 요청 중...';
    
    statusBox.classList.remove('hidden');
    statusLog.textContent = 'Meta Graph API 파이프라인 가동 시작...\n';
    fallbackActions.classList.add('hidden');

    try {
        const response = await fetch('/api/publish', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                image_paths: currentPostData.image_paths,
                caption: captionText.value, // Read edited caption directly from textarea
                date_str: currentPostData.date_str
            })
        });

        const data = await response.json();
        
        statusLog.textContent += data.log + '\n';
        
        if (response.ok && data.success) {
            statusLog.textContent += `🎉 게시 완료! 포스트 ID: ${data.post_id}\n`;
            alert('인스타그램 발행에 성공했습니다!');
            publishBtn.textContent = '🚀 Instagram에 즉시 발행';
            publishBtn.disabled = false;
        } else {
            statusLog.textContent += `❌ 발행 실패: ${data.error || '알 수 없는 오류'}\n`;
            
            // Set up fallback download ZIP link
            if (data.zip_path) {
                downloadZipBtn.href = '/' + data.zip_path;
                fallbackActions.classList.remove('hidden');
            }
            
            alert('인스타그램 발행에 실패했습니다. 수동 다운로드 및 캡션 복사 기능을 활성화합니다.');
            publishBtn.textContent = '🚀 Instagram에 즉시 발행';
            publishBtn.disabled = false;
        }
    } catch (error) {
        console.error(error);
        statusLog.textContent += `❌ 오류 발생: ${error.message}\n`;
        alert('요청 중 문제가 발생했습니다. 로그를 확인해 주세요.');
        publishBtn.textContent = '🚀 Instagram에 즉시 발행';
        publishBtn.disabled = false;
    }
});

// Initialize backgrounds on load
window.addEventListener('DOMContentLoaded', () => {
    initializeBackgroundRotation();
    
    // Modal Close Handlers
    const imageModal = document.getElementById('image-modal');
    const modalClose = document.querySelector('.modal-close');
    if (imageModal && modalClose) {
        modalClose.addEventListener('click', () => {
            imageModal.classList.add('hidden');
        });
        // Close on clicking overlay background
        imageModal.addEventListener('click', (e) => {
            if (e.target === imageModal || e.target.classList.contains('modal-content-wrapper')) {
                imageModal.classList.add('hidden');
            }
        });
        // Close on Escape key press
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') {
                imageModal.classList.add('hidden');
            }
        });
    }
});
