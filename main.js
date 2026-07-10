// Global State for current generation
let currentPostData = {
    image_paths: [],
    caption: '',
    date_str: '',
    zip_url: '',
    title: ''
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
const titleEditInput = document.getElementById('title-edit-input');
const updateTitleBtn = document.getElementById('update-title-btn');
const saveBtn = document.getElementById('save-btn');
const reelBtn = document.getElementById('reel-btn');
const saveVideoBtn = document.getElementById('save-video-btn');

// Hide the "영상 저장" button (a previously built reel is stale once the
// underlying card images change).
function resetReelButton() {
    if (saveVideoBtn) {
        saveVideoBtn.classList.add('hidden');
        saveVideoBtn.href = '#';
    }
}

// Helper to render slides in grid
function renderSlidesPreview(imageUrls) {
    slidesGrid.innerHTML = '';
    imageUrls.forEach((url, index) => {
        const wrapper = document.createElement('div');
        wrapper.className = 'slide-preview-wrapper';
        wrapper.style.cursor = 'pointer';
        
        const img = document.createElement('img');
        img.src = url + '?t=' + Date.now();
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
            modalImg.src = url + '?t=' + Date.now();
        });
        
        slidesGrid.appendChild(wrapper);
    });
}

// 1. Generate Content
generateBtn.addEventListener('click', async () => {
    const url = urlInput.value.strip ? urlInput.value.strip() : urlInput.value.trim();
    
    // Show Loading Overlay
    loadingOverlay.classList.remove('hidden');
    resultsSection.classList.add('hidden');

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
            currentPostData.zip_url = data.zip_url;
            currentPostData.title = data.title;
            
            // Populate UI Elements
            dateBadge.textContent = data.date_str.split('/')[0];
            captionText.value = data.plan.final_caption;
            captionText.readOnly = false;
            captionText.removeAttribute('readonly');
            
            // Set cover title input
            titleEditInput.value = data.title;
            
            // Render Slide Images Preview
            renderSlidesPreview(data.image_urls);

            // A freshly generated post has no reel yet
            resetReelButton();

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

// 3. Update Slide Title
updateTitleBtn.addEventListener('click', async () => {
    const newTitle = titleEditInput.value.trim();
    if (!newTitle) {
        alert('첫 번째 이미지에 적용할 제목을 입력해 주세요.');
        return;
    }

    if (!currentPostData.date_str) {
        alert('변경할 콘텐츠가 존재하지 않습니다. 먼저 생성해 주세요.');
        return;
    }

    loadingOverlay.classList.remove('hidden');

    try {
        const response = await fetch('/api/update_title', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                date_str: currentPostData.date_str,
                title: newTitle
            })
        });

        if (!response.ok) {
            throw new Error(`제목 수정 중 서버 에러 발생 (상태 코드: ${response.status})`);
        }

        const data = await response.json();

        if (data.success) {
            currentPostData.zip_url = data.zip_url;
            currentPostData.title = newTitle;
            currentPostData.image_paths = data.absolute_paths;

            // Render Slide Images Preview
            renderSlidesPreview(data.image_urls);

            // Images changed -> any previously built reel is now stale
            resetReelButton();

            alert('표지 제목이 성공적으로 변경되었습니다!');
        } else {
            alert(`제목 변경 실패: ${data.error || '알 수 없는 오류'}`);
        }
    } catch (error) {
        console.error(error);
        alert(`요청 처리 중 오류가 발생했습니다: ${error.message}`);
    } finally {
        loadingOverlay.classList.add('hidden');
    }
});

// 4. Save/Download Zip Package
saveBtn.addEventListener('click', async (e) => {
    e.preventDefault();

    if (!currentPostData.date_str) {
        alert('저장할 콘텐츠가 없습니다. 먼저 콘텐츠를 생성해 주세요.');
        return;
    }

    saveBtn.style.pointerEvents = 'none';
    saveBtn.style.opacity = '0.6';
    const originalText = saveBtn.innerHTML;
    saveBtn.innerHTML = '⏳ 다운로드 준비 중...';

    try {
        const response = await fetch('/api/prepare_download', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                date_str: currentPostData.date_str,
                title: titleEditInput.value.trim(),
                caption: captionText.value
            })
        });

        if (!response.ok) {
            throw new Error(`서버 에러 발생 (상태 코드: ${response.status})`);
        }

        const data = await response.json();

        if (data.success) {
            currentPostData.zip_url = data.zip_url;

            // Create temporary link to trigger download
            const tempLink = document.createElement('a');
            tempLink.href = data.zip_url;
            tempLink.download = data.zip_url.split('/').pop();
            document.body.appendChild(tempLink);
            tempLink.click();
            document.body.removeChild(tempLink);
        } else {
            alert(`이미지 저장 실패: ${data.error || '알 수 없는 오류'}`);
        }
    } catch (error) {
        console.error(error);
        alert(`다운로드 중 문제가 발생했습니다: ${error.message}`);
    } finally {
        saveBtn.style.pointerEvents = 'auto';
        saveBtn.style.opacity = '1';
        saveBtn.innerHTML = originalText;
    }
});

// 5. Create Reels Video from the generated cards
reelBtn.addEventListener('click', async () => {
    if (!currentPostData.date_str) {
        alert('영상으로 만들 콘텐츠가 없습니다. 먼저 콘텐츠를 생성해 주세요.');
        return;
    }

    const originalText = reelBtn.innerHTML;
    reelBtn.disabled = true;
    reelBtn.style.opacity = '0.6';
    reelBtn.style.pointerEvents = 'none';
    reelBtn.innerHTML = '🎬 영상 만드는 중...';

    // Reuse the fullscreen loader with a reel-specific message
    const loadingSub = document.querySelector('.loading-sub');
    const originalSub = loadingSub ? loadingSub.textContent : '';
    if (loadingSub) loadingSub.textContent = '카드 이미지를 이어붙여 릴스 영상을 만드는 중입니다.';
    loadingOverlay.classList.remove('hidden');

    try {
        const response = await fetch('/api/create_reel', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ date_str: currentPostData.date_str })
        });

        if (!response.ok) {
            throw new Error(`서버 에러 발생 (상태 코드: ${response.status})`);
        }

        const data = await response.json();

        if (data.success) {
            // Reveal the "영상 저장" download button
            saveVideoBtn.href = data.reel_url + '?t=' + Date.now();
            saveVideoBtn.download = 'reel.mp4';
            saveVideoBtn.classList.remove('hidden');
        } else {
            alert(`릴스 제작 실패: ${data.error || '알 수 없는 오류'}`);
        }
    } catch (error) {
        console.error(error);
        alert(`릴스 제작 중 오류가 발생했습니다: ${error.message}`);
    } finally {
        loadingOverlay.classList.add('hidden');
        if (loadingSub) loadingSub.textContent = originalSub;
        reelBtn.disabled = false;
        reelBtn.style.opacity = '1';
        reelBtn.style.pointerEvents = 'auto';
        reelBtn.innerHTML = originalText;
    }
});

// Initialize backgrounds on load
window.addEventListener('DOMContentLoaded', () => {
    initializeBackgroundRotation();
    
    // Explicitly make sure caption text area is editable
    const captionText = document.getElementById('caption-text');
    if (captionText) {
        captionText.readOnly = false;
        captionText.removeAttribute('readonly');
    }
    
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
