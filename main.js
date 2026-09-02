// Global State for current generation
let currentPostData = {
    image_paths: [],
    caption: '',
    date_str: '',
    zip_url: '',
    title: '',
    subtitle: '',      // up to 3 lines drawn under the cover title
    theme: '',         // accent color: rolled at random, then user-selectable
    mode: 'carousel'   // 'carousel' = multi-card deck, 'single' = one-card post
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

// --- Presenter Access Key ---
// Paid endpoints require an "X-Access-Key" header that only the presenter has.
// The presenter opens the site once as `.../?key=YOUR_KEY`; the key is saved to
// this browser and stripped from the visible URL. Visitors without the key are
// prompted, and cannot generate unless they know it.
const ACCESS_KEY_STORAGE = 'presenter_access_key';

function getStoredAccessKey() {
    return localStorage.getItem(ACCESS_KEY_STORAGE) || '';
}

function setStoredAccessKey(key) {
    if (key) localStorage.setItem(ACCESS_KEY_STORAGE, key);
}

// Capture `?key=` from the URL (presenter convenience), then remove it from the
// address bar so it isn't shown on screen or left in history during the demo.
function captureAccessKeyFromUrl() {
    const params = new URLSearchParams(window.location.search);
    const key = params.get('key');
    if (key) {
        setStoredAccessKey(key);
        params.delete('key');
        const clean = window.location.pathname + (params.toString() ? '?' + params.toString() : '');
        window.history.replaceState({}, document.title, clean);
    }
}

// Shows a masked (password) input modal and resolves with the entered value
// ('' if cancelled). Falls back to a native prompt if the markup is missing.
function promptPassword() {
    return new Promise((resolve) => {
        const modal = document.getElementById('password-modal');
        const input = document.getElementById('password-input');
        const okBtn = document.getElementById('password-ok-btn');
        const cancelBtn = document.getElementById('password-cancel-btn');

        if (!modal || !input || !okBtn || !cancelBtn) {
            resolve((window.prompt('생성하려면 비밀번호를 입력하세요:') || '').trim());
            return;
        }

        input.value = '';
        modal.classList.remove('hidden');
        setTimeout(() => input.focus(), 50);

        const cleanup = () => {
            modal.classList.add('hidden');
            okBtn.removeEventListener('click', onOk);
            cancelBtn.removeEventListener('click', onCancel);
            input.removeEventListener('keydown', onKey);
        };
        const onOk = () => { const v = input.value.trim(); cleanup(); resolve(v); };
        const onCancel = () => { cleanup(); resolve(''); };
        const onKey = (e) => {
            if (e.key === 'Enter') { e.preventDefault(); onOk(); }
            else if (e.key === 'Escape') { e.preventDefault(); onCancel(); }
        };

        okBtn.addEventListener('click', onOk);
        cancelBtn.addEventListener('click', onCancel);
        input.addEventListener('keydown', onKey);
    });
}

// Returns the saved password, or prompts for it the first time and remembers it.
async function ensureAccessKey() {
    let key = getStoredAccessKey();
    if (!key) {
        key = await promptPassword();
        setStoredAccessKey(key);
    }
    return key;
}

// fetch wrapper that attaches the access key and surfaces a clear 401 message.
async function apiFetch(url, options = {}) {
    const key = await ensureAccessKey();
    const headers = Object.assign({}, options.headers, { 'X-Access-Key': key });
    const response = await fetch(url, Object.assign({}, options, { headers }));
    if (response.status === 401) {
        // Wrong/empty key: forget it so the next attempt can re-prompt.
        localStorage.removeItem(ACCESS_KEY_STORAGE);
        throw new Error('접근 권한이 없습니다. 발표자 전용 액세스 키가 필요합니다.');
    }
    return response;
}

// --- API Orchestration & UI Control ---

const urlInput = document.getElementById('url-input');
const generateBtn = document.getElementById('generate-btn');
const generateOneBtn = document.getElementById('generate-one-btn');
const resultsSection = document.getElementById('results-section');
const loadingOverlay = document.getElementById('loading-overlay');
const dateBadge = document.getElementById('date-badge');
const slidesGrid = document.getElementById('slides-grid');
const captionText = document.getElementById('caption-text');
const copyCaptionBtn = document.getElementById('copy-caption-btn');
const titleEditInput = document.getElementById('title-edit-input');
const coverSubInput = document.getElementById('cover-sub-input');
const updateTitleBtn = document.getElementById('update-title-btn');
const themeSwatches = document.getElementById('theme-swatches');
const saveBtn = document.getElementById('save-btn');
const previewHeading = document.getElementById('preview-heading');
const insertHint = document.getElementById('insert-hint');
const reelBtn = document.getElementById('reel-btn');
const saveVideoBtn = document.getElementById('save-video-btn');
const reelYtBtn = document.getElementById('reel-yt-btn');
const saveVideoYtBtn = document.getElementById('save-video-yt-btn');
const shortsBtn = document.getElementById('shorts-btn');
const saveShortsBtn = document.getElementById('save-shorts-btn');

// --- Background photo attached on the main screen ---
// A photo picked here becomes the post's background image (used crisp on the
// cover, blurred behind the other cards). With no photo attached, generation
// works exactly as before and the AI creates the background.
const bgUploadBtn = document.getElementById('bg-upload-btn');
const bgFileRow = document.getElementById('bg-file-row');
const bgFileThumb = document.getElementById('bg-file-thumb');
const bgFileName = document.getElementById('bg-file-name');
const bgFileClear = document.getElementById('bg-file-clear');

let selectedBgFile = null;
let bgFileInput = null;   // own picker, separate from the per-card photo one

function getBgFileInput() {
    if (!bgFileInput) {
        bgFileInput = document.createElement('input');
        bgFileInput.type = 'file';
        bgFileInput.accept = 'image/*';
        bgFileInput.style.display = 'none';
        document.body.appendChild(bgFileInput);
        bgFileInput.addEventListener('change', (e) => {
            const file = e.target.files && e.target.files[0];
            e.target.value = ''; // allow re-picking the same file
            if (file) setSelectedBgFile(file);
        });
    }
    return bgFileInput;
}

// Shows/clears the "attached photo" row and keeps the button label in sync.
function setSelectedBgFile(file) {
    if (bgFileThumb && bgFileThumb.src.startsWith('blob:')) {
        URL.revokeObjectURL(bgFileThumb.src);
    }
    selectedBgFile = file || null;

    if (!selectedBgFile) {
        if (bgFileThumb) bgFileThumb.removeAttribute('src');
        if (bgFileRow) bgFileRow.classList.add('hidden');
        if (bgUploadBtn) bgUploadBtn.textContent = '📷 사진 첨부';
        return;
    }

    if (bgFileThumb) bgFileThumb.src = URL.createObjectURL(selectedBgFile);
    if (bgFileName) bgFileName.textContent = selectedBgFile.name;
    if (bgFileRow) bgFileRow.classList.remove('hidden');
    if (bgUploadBtn) bgUploadBtn.textContent = '📷 사진 변경';
}

if (bgUploadBtn) {
    bgUploadBtn.addEventListener('click', () => getBgFileInput().click());
}
if (bgFileClear) {
    bgFileClear.addEventListener('click', () => setSelectedBgFile(null));
}

// Hide every "영상 저장" button (a previously built video is stale once the
// underlying card images change).
function resetReelButton() {
    [saveVideoBtn, saveVideoYtBtn, saveShortsBtn].forEach((btn) => {
        if (btn) {
            btn.classList.add('hidden');
            btn.href = '#';
        }
    });
}

// --- Sub-copy under the title ---
// On a carousel this box holds the three cover lines. On a one-card post it
// holds that card's body block, which stretches to five lines when the article
// has more the reader must not miss. The renderer honours the same caps, so trim
// anything typed or pasted beyond them: what you see is what the card gets.
const COVER_SUB_MAX_LINES = 3;
const SINGLE_BODY_MAX_LINES = 5;

function subMaxLines() {
    return currentPostData.mode === 'single' ? SINGLE_BODY_MAX_LINES : COVER_SUB_MAX_LINES;
}

function clampCoverSub(value) {
    return (value || '').split('\n').slice(0, subMaxLines()).join('\n');
}

if (coverSubInput) {
    coverSubInput.addEventListener('input', () => {
        const clamped = clampCoverSub(coverSubInput.value);
        if (clamped !== coverSubInput.value) coverSubInput.value = clamped;
    });
    // Enter on the last allowed line would only add a line the card drops.
    coverSubInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && coverSubInput.value.split('\n').length >= subMaxLines()) {
            e.preventDefault();
        }
    });
}

// --- Accent color picker ---
// The accent color is rolled at random each time a post is generated. These
// chips let the user pick one instead: the cards are redrawn from the stored
// plan and background, so switching color costs no API call.

// Used only when /api/themes is unreachable (e.g. an older server still
// deployed). Keep in sync with THEMES in src/script_vision.py.
const FALLBACK_THEMES = [
    { name: 'orange', hex: '#ff6600' },
    { name: 'blue',   hex: '#0a84ff' },
    { name: 'green',  hex: '#22c55e' },
    { name: 'purple', hex: '#9561f6' },
    { name: 'pink',   hex: '#f43f5e' },
    { name: 'teal',   hex: '#14b8a6' },
    { name: 'yellow', hex: '#facc15' },
    { name: 'red',    hex: '#ff3b30' }
];

const THEME_LABELS = {
    orange: '오렌지', blue: '블루', green: '그린', purple: '퍼플',
    pink: '핑크', teal: '틸', yellow: '옐로우', red: '레드'
};

let availableThemes = null;   // fetched once, then reused

async function loadThemes() {
    if (availableThemes) return availableThemes;
    try {
        // No access key needed: this reads nothing and costs nothing.
        const response = await fetch('/api/themes');
        if (response.ok) {
            const data = await response.json();
            if (data.success && Array.isArray(data.themes) && data.themes.length) {
                availableThemes = data.themes;
                return availableThemes;
            }
        }
    } catch (error) {
        console.warn('색상 목록을 불러오지 못해 기본 목록을 사용합니다.', error);
    }
    availableThemes = FALLBACK_THEMES;
    return availableThemes;
}

async function renderThemePicker() {
    if (!themeSwatches) return;
    const themes = await loadThemes();
    themeSwatches.innerHTML = '';
    themes.forEach(({ name, hex }) => {
        const label = THEME_LABELS[name] || name;
        const chip = document.createElement('button');
        chip.type = 'button';
        chip.className = 'theme-swatch';
        chip.style.background = hex;
        chip.title = label;
        chip.setAttribute('aria-label', label + ' 색상으로 변경');
        chip.setAttribute('aria-pressed', String(name === currentPostData.theme));
        chip.classList.toggle('active', name === currentPostData.theme);
        chip.addEventListener('click', () => applyTheme(name));
        themeSwatches.appendChild(chip);
    });
}

async function applyTheme(theme) {
    if (!currentPostData.date_str) {
        alert('먼저 콘텐츠를 생성해 주세요.');
        return;
    }
    if (theme === currentPostData.theme) return;   // already this color

    loadingOverlay.classList.remove('hidden');
    try {
        const response = await apiFetch('/api/update_theme', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ date_str: currentPostData.date_str, theme })
        });
        if (!response.ok) {
            let msg = `서버 에러 (상태 코드: ${response.status})`;
            try { const j = await response.json(); if (j.detail) msg = j.detail; } catch (_) {}
            throw new Error(msg);
        }
        const data = await response.json();
        if (data.success) {
            currentPostData.theme = data.theme || theme;
            renderThemePicker();
            renderSlidesPreview(data.image_urls, data.photo_slides);
            // The card artwork changed -> any previously built video is now stale.
            resetReelButton();
        }
    } catch (error) {
        console.error(error);
        alert(`색상 변경 중 오류가 발생했습니다: ${error.message}`);
    } finally {
        loadingOverlay.classList.add('hidden');
    }
}

// --- Attach / remove a user photo on a card ---
// A photo is not its own slide: it is drawn across the top of the card you pick,
// and that card's copy shrinks and moves underneath it.
let currentImageUrls = [];
let currentPhotoSlides = [];   // filenames of cards that already carry a photo
let pendingPhotoTarget = null; // filename of the card awaiting a file pick
let hiddenFileInput = null;

// Sentinel target: the picked photo replaces the post's background instead of
// going on top of one card (used by the one-card post, whose photo IS the card).
const BACKGROUND_TARGET = '__background__';

// A single reusable hidden file picker for photo insertion.
function getHiddenFileInput() {
    if (!hiddenFileInput) {
        hiddenFileInput = document.createElement('input');
        hiddenFileInput.type = 'file';
        hiddenFileInput.accept = 'image/*';
        hiddenFileInput.style.display = 'none';
        document.body.appendChild(hiddenFileInput);
        hiddenFileInput.addEventListener('change', async (e) => {
            const file = e.target.files && e.target.files[0];
            const target = pendingPhotoTarget;
            e.target.value = ''; // allow re-selecting the same file next time
            pendingPhotoTarget = null;
            if (!file || target === null) return;
            if (target === BACKGROUND_TARGET) {
                await replaceBackgroundWith(file);
            } else {
                await attachPhotoTo(target, file);
            }
        });
    }
    return hiddenFileInput;
}

// Opens the file picker; the chosen photo goes on top of card `filename`
// (or becomes the post background when `filename` is BACKGROUND_TARGET).
function triggerPhotoFor(filename) {
    if (!currentPostData.date_str) {
        alert('먼저 콘텐츠를 생성해 주세요.');
        return;
    }
    pendingPhotoTarget = filename;
    getHiddenFileInput().click();
}

// Redraws the post on a newly uploaded background photo. Costs no API call:
// the card copy is reused from the saved plan.
async function replaceBackgroundWith(file) {
    loadingOverlay.classList.remove('hidden');
    try {
        const form = new FormData();
        form.append('date_str', currentPostData.date_str);
        form.append('file', file);

        const response = await apiFetch('/api/replace_background', { method: 'POST', body: form });
        if (!response.ok) {
            let msg = `서버 에러 (상태 코드: ${response.status})`;
            try { const j = await response.json(); if (j.detail) msg = j.detail; } catch (_) {}
            throw new Error(msg);
        }
        const data = await response.json();
        if (data.success) {
            renderSlidesPreview(data.image_urls, data.photo_slides);
            resetReelButton();
        }
    } catch (error) {
        console.error(error);
        alert(`배경 사진 변경 중 오류가 발생했습니다: ${error.message}`);
    } finally {
        loadingOverlay.classList.add('hidden');
    }
}

async function attachPhotoTo(filename, file) {
    loadingOverlay.classList.remove('hidden');
    try {
        const form = new FormData();
        form.append('date_str', currentPostData.date_str);
        form.append('target', filename);
        form.append('file', file);

        const response = await apiFetch('/api/insert_image', { method: 'POST', body: form });
        if (!response.ok) {
            let msg = `서버 에러 (상태 코드: ${response.status})`;
            try { const j = await response.json(); if (j.detail) msg = j.detail; } catch (_) {}
            throw new Error(msg);
        }
        const data = await response.json();
        if (data.success) {
            renderSlidesPreview(data.image_urls, data.photo_slides);
            // The card artwork changed -> any previously built reel is now stale.
            resetReelButton();
        }
    } catch (error) {
        console.error(error);
        alert(`사진 삽입 중 오류가 발생했습니다: ${error.message}`);
    } finally {
        loadingOverlay.classList.add('hidden');
    }
}

// Detaches the photo from a card; the card goes back to the full-size copy layout.
async function removePhotoFrom(filename) {
    if (!confirm('이 카드에서 사진을 뺄까요?')) return;
    loadingOverlay.classList.remove('hidden');
    try {
        const response = await apiFetch('/api/remove_photo', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ date_str: currentPostData.date_str, filename })
        });
        if (!response.ok) {
            let msg = `서버 에러 (상태 코드: ${response.status})`;
            try { const j = await response.json(); if (j.detail) msg = j.detail; } catch (_) {}
            throw new Error(msg);
        }
        const data = await response.json();
        if (data.success) {
            renderSlidesPreview(data.image_urls, data.photo_slides);
            resetReelButton();
        }
    } catch (error) {
        console.error(error);
        alert(`사진 삭제 중 오류가 발생했습니다: ${error.message}`);
    } finally {
        loadingOverlay.classList.add('hidden');
    }
}

// Legacy standalone photo cards (extra_*.jpg) from older posts can still be removed.
async function deleteImage(filename) {
    if (!confirm('이 사진을 목록에서 삭제할까요?')) return;
    loadingOverlay.classList.remove('hidden');
    try {
        const response = await apiFetch('/api/delete_image', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ date_str: currentPostData.date_str, filename })
        });
        if (!response.ok) {
            throw new Error(`서버 에러 (상태 코드: ${response.status})`);
        }
        const data = await response.json();
        if (data.success) {
            renderSlidesPreview(data.image_urls, data.photo_slides);
            resetReelButton();
        }
    } catch (error) {
        console.error(error);
        alert(`사진 삭제 중 오류가 발생했습니다: ${error.message}`);
    } finally {
        loadingOverlay.classList.add('hidden');
    }
}

// Helper to render slides in grid
function renderSlidesPreview(imageUrls, photoSlides) {
    const isSingle = currentPostData.mode === 'single';
    currentImageUrls = imageUrls.slice();
    currentPhotoSlides = Array.isArray(photoSlides) ? photoSlides.slice() : currentPhotoSlides;
    slidesGrid.classList.toggle('single-card', isSingle);
    slidesGrid.innerHTML = '';
    imageUrls.forEach((url, index) => {
        const filename = url.split('/').pop().split('?')[0];
        const isExtra = filename.startsWith('extra_');   // standalone photo from an older post
        const isCover = index === 0;                     // the cover keeps its full-bleed artwork
        const hasPhoto = currentPhotoSlides.includes(filename);

        const wrapper = document.createElement('div');
        wrapper.className = 'slide-preview-wrapper';
        wrapper.style.cursor = 'pointer';
        wrapper.style.position = 'relative';

        const img = document.createElement('img');
        img.src = url + '?t=' + Date.now();
        img.alt = `Slide ${index + 1}`;

        const badge = document.createElement('div');
        badge.className = 'slide-number';
        badge.textContent = index + 1;

        wrapper.appendChild(img);
        wrapper.appendChild(badge);

        // Legacy standalone photo cards get a label and a delete button.
        if (isExtra) {
            const tag = document.createElement('div');
            tag.className = 'slide-extra-tag';
            tag.textContent = '내 사진';
            wrapper.appendChild(tag);

            const del = document.createElement('button');
            del.type = 'button';
            del.className = 'slide-del-btn';
            del.textContent = '×';
            del.title = '이 사진 삭제';
            del.addEventListener('click', (e) => {
                e.stopPropagation();
                deleteImage(filename);
            });
            wrapper.appendChild(del);
        }

        // Cards carrying a photo get a label and a button to take it back off.
        if (hasPhoto) {
            const tag = document.createElement('div');
            tag.className = 'slide-extra-tag';
            tag.textContent = '내 사진';
            wrapper.appendChild(tag);

            const del = document.createElement('button');
            del.type = 'button';
            del.className = 'slide-del-btn';
            del.textContent = '×';
            del.title = '이 카드에서 사진 빼기';
            del.addEventListener('click', (e) => {
                e.stopPropagation();
                removePhotoFrom(filename);
            });
            wrapper.appendChild(del);
        }

        // The one-card post is drawn straight onto its background photo, so its
        // button swaps that photo instead of stacking one on top of the card.
        if (isSingle) {
            const bg = document.createElement('button');
            bg.type = 'button';
            bg.className = 'slide-insert-btn';
            bg.textContent = '📷 사진 교체';
            bg.title = '이 카드의 배경 사진 바꾸기';
            bg.addEventListener('click', (e) => {
                e.stopPropagation();
                triggerPhotoFor(BACKGROUND_TARGET);
            });
            wrapper.appendChild(bg);
        }
        // "Put a photo on top of this card" button (not on the cover or legacy photo cards).
        else if (!isExtra && !isCover) {
            const ins = document.createElement('button');
            ins.type = 'button';
            ins.className = 'slide-insert-btn';
            ins.textContent = hasPhoto ? '사진 교체' : '＋ 사진';
            ins.title = '이 카드 상단에 사진 넣기';
            ins.addEventListener('click', (e) => {
                e.stopPropagation();
                triggerPhotoFor(filename);
            });
            wrapper.appendChild(ins);
        }

        // Click image to open preview modal
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
// The two buttons run the same pipeline; `mode` picks the format:
// 'carousel' = the multi-card deck, 'single' = a one-card post.
const MODE_COPY = {
    carousel: {
        heading: '카드뉴스 슬라이드 프리뷰',
        hint: '각 카드의 <b>＋ 사진</b> 버튼을 누르면 그 카드 <b>상단에 사진</b>이 들어가고, 글은 작아지면서 아래쪽으로 내려갑니다. 표지에는 넣을 수 없어요.',
        subPlaceholder: '제목 바로 아래에 들어갈 내용을 최대 3줄까지 입력하세요. (비워두면 제목만 들어갑니다)'
    },
    single: {
        heading: '1장 카드뉴스 프리뷰',
        hint: '카드에 마우스를 올리면 나오는 <b>📷 사진 교체</b> 버튼으로 배경 사진을 바꿀 수 있어요. (사진만 바꾸는 거라 추가 비용은 들지 않습니다.)',
        subPlaceholder: '제목 아래 본문입니다. 중요한 내용이 많으면 최대 5줄까지 쓸 수 있어요. (비워두면 제목만 들어갑니다)'
    }
};

// Reshapes the results area for the format that was just generated. A one-card
// post has nothing to swipe through, so the reel/YouTube buttons step aside and
// the 3-second shorts cut takes their place.
function applyModeUI(mode) {
    const copy = MODE_COPY[mode] || MODE_COPY.carousel;
    if (previewHeading) previewHeading.textContent = copy.heading;
    if (insertHint) insertHint.innerHTML = copy.hint;

    const isSingle = mode === 'single';

    // The same box takes three cover lines or five one-card body lines, so it
    // grows and relabels itself with the format.
    if (coverSubInput) {
        coverSubInput.rows = isSingle ? SINGLE_BODY_MAX_LINES : COVER_SUB_MAX_LINES;
        if (copy.subPlaceholder) coverSubInput.placeholder = copy.subPlaceholder;
    }

    [reelBtn, reelYtBtn].forEach((btn) => {
        if (btn) btn.classList.toggle('hidden', isSingle);
    });
    if (shortsBtn) shortsBtn.classList.toggle('hidden', !isSingle);
}

async function runGenerate(mode) {
    const url = urlInput.value.trim();

    // Ask for the password first (only the first time), before any loading UI.
    if (!(await ensureAccessKey())) {
        alert('비밀번호를 입력해야 생성할 수 있습니다.');
        return;
    }

    // Show Loading Overlay
    loadingOverlay.classList.remove('hidden');
    resultsSection.classList.add('hidden');

    try {
        // Multipart, so the optional background photo can ride along with the URL.
        // (No Content-Type header: the browser sets the multipart boundary.)
        const form = new FormData();
        form.append('url', url || '');
        form.append('mode', mode);
        if (selectedBgFile) form.append('background', selectedBgFile);

        const response = await apiFetch('/api/generate', { method: 'POST', body: form });

        if (!response.ok) {
            let msg = `서버 에러 발생 (상태 코드: ${response.status})`;
            try { const j = await response.json(); if (j.detail) msg = j.detail; } catch (_) {}
            throw new Error(msg);
        }

        const data = await response.json();
        
        if (data.success) {
            // Update Global State
            currentPostData.image_paths = data.absolute_paths;
            currentPostData.caption = data.plan.final_caption;
            currentPostData.date_str = data.date_str;
            currentPostData.zip_url = data.zip_url;
            currentPostData.title = data.title;
            currentPostData.mode = data.mode || 'carousel';
            // The accent color the backend rolled for this post, so the picker
            // can show which chip is currently in use.
            currentPostData.theme = (data.plan && data.plan.theme) || '';
            applyModeUI(currentPostData.mode);
            renderThemePicker();

            // Populate UI Elements
            dateBadge.textContent = data.date_str.split('/')[0];
            captionText.value = data.plan.final_caption;
            captionText.readOnly = false;
            captionText.removeAttribute('readonly');
            
            // Set cover title input
            titleEditInput.value = data.title;

            // The cover sub-copy: empty on a carousel (nothing is drawn under
            // the title until the user types something), pre-filled on a
            // one-card post whose body text the AI already wrote.
            const coverSlide = (data.plan && data.plan.slides && data.plan.slides[0]) || {};
            currentPostData.subtitle = clampCoverSub(coverSlide.sub_text || '');
            if (coverSubInput) coverSubInput.value = currentPostData.subtitle;

            // Render Slide Images Preview
            renderSlidesPreview(data.image_urls, data.photo_slides || []);

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
}

generateBtn.addEventListener('click', () => runGenerate('carousel'));
if (generateOneBtn) {
    generateOneBtn.addEventListener('click', () => runGenerate('single'));
}

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
// Title and sub-copy travel together: one round trip redraws both.
updateTitleBtn.addEventListener('click', async () => {
    const newTitle = titleEditInput.value.trim();
    const newSubtitle = coverSubInput ? clampCoverSub(coverSubInput.value) : '';
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
        const response = await apiFetch('/api/update_title', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                date_str: currentPostData.date_str,
                title: newTitle,
                subtitle: newSubtitle
            })
        });

        if (!response.ok) {
            throw new Error(`제목 수정 중 서버 에러 발생 (상태 코드: ${response.status})`);
        }

        const data = await response.json();

        if (data.success) {
            currentPostData.zip_url = data.zip_url;
            currentPostData.title = newTitle;
            currentPostData.subtitle = newSubtitle;
            currentPostData.image_paths = data.absolute_paths;

            // Render Slide Images Preview
            renderSlidesPreview(data.image_urls, data.photo_slides);

            // Images changed -> any previously built reel is now stale
            resetReelButton();

            alert('표지 문구가 성공적으로 변경되었습니다!');
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
        const response = await apiFetch('/api/prepare_download', {
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

// 5. Build a video from the generated cards — 9:16 for Reels, 16:9 for YouTube.
// Neither shape crops the cards; the leftover area gets a blurred backdrop.
async function buildVideo({ orientation, button, saveButton, label, downloadName }) {
    if (!currentPostData.date_str) {
        alert('영상으로 만들 콘텐츠가 없습니다. 먼저 콘텐츠를 생성해 주세요.');
        return;
    }

    const originalText = button.innerHTML;
    button.disabled = true;
    button.style.opacity = '0.6';
    button.style.pointerEvents = 'none';
    button.innerHTML = '🎬 영상 만드는 중...';

    // Reuse the fullscreen loader with a video-specific message
    const loadingSub = document.querySelector('.loading-sub');
    const originalSub = loadingSub ? loadingSub.textContent : '';
    if (loadingSub) loadingSub.textContent = `카드 이미지를 이어붙여 ${label} 영상을 만드는 중입니다.`;
    loadingOverlay.classList.remove('hidden');

    try {
        const response = await apiFetch('/api/create_reel', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ date_str: currentPostData.date_str, orientation })
        });

        if (!response.ok) {
            throw new Error(`서버 에러 발생 (상태 코드: ${response.status})`);
        }

        const data = await response.json();

        if (data.success) {
            // Reveal the matching "영상 저장" download button
            saveButton.href = data.reel_url + '?t=' + Date.now();
            saveButton.download = downloadName;
            saveButton.classList.remove('hidden');
        } else {
            alert(`${label} 제작 실패: ${data.error || '알 수 없는 오류'}`);
        }
    } catch (error) {
        console.error(error);
        alert(`${label} 제작 중 오류가 발생했습니다: ${error.message}`);
    } finally {
        loadingOverlay.classList.add('hidden');
        if (loadingSub) loadingSub.textContent = originalSub;
        button.disabled = false;
        button.style.opacity = '1';
        button.style.pointerEvents = 'auto';
        button.innerHTML = originalText;
    }
}

reelBtn.addEventListener('click', () => buildVideo({
    orientation: 'vertical',
    button: reelBtn,
    saveButton: saveVideoBtn,
    label: '릴스',
    downloadName: 'reel.mp4'
}));

reelYtBtn.addEventListener('click', () => buildVideo({
    orientation: 'horizontal',
    button: reelYtBtn,
    saveButton: saveVideoYtBtn,
    label: '유튜브',
    downloadName: 'youtube.mp4'
}));

// The one-card post's 3-second 9:16 cut for Shorts/Reels.
if (shortsBtn) {
    shortsBtn.addEventListener('click', () => buildVideo({
        orientation: 'shorts',
        button: shortsBtn,
        saveButton: saveShortsBtn,
        label: '쇼츠',
        downloadName: 'shorts.mp4'
    }));
}

// Initialize backgrounds on load
window.addEventListener('DOMContentLoaded', () => {
    // Capture the presenter access key from `?key=` before anything else.
    captureAccessKeyFromUrl();

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
