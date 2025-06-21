document.addEventListener('DOMContentLoaded', function () {
  // Get elements
  const fileForm = document.getElementById('fileForm');
  const textForm = document.getElementById('textForm');
  const fileInput = document.getElementById('fileInput');
  const fileUpload = document.querySelector('.file-upload');
  const fileInfo = document.getElementById('fileInfo');
  const fileSubmitBtn = document.getElementById('fileSubmitBtn');
  const textSubmitBtn = document.getElementById('textSubmitBtn');
  const textArea = document.getElementById('inputText');
  const charCounter = document.getElementById('charCounter');
  const errorDiv = document.getElementById('errorDiv');
  const loadingDiv = document.getElementById('loadingDiv');
  const resultDiv = document.getElementById('resultDiv');
  const resultContent = document.getElementById('resultContent');

  // Tab switching
  window.switchTab = function (tabName) {
    // Update tab buttons
    document.querySelectorAll('.tab').forEach(tab => tab.classList.remove('active'));
    event.target.classList.add('active');

    // Update tab content
    document.querySelectorAll('.tab-content').forEach(content => content.classList.remove('active'));
    document.getElementById(tabName + 'Tab').classList.add('active');
  };

  // File upload handling
  fileInput.addEventListener('change', function (e) {
    const file = e.target.files[0];
    if (file) {
      displayFileInfo(file);
      fileSubmitBtn.disabled = false;
    } else {
      hideFileInfo();
      fileSubmitBtn.disabled = true;
    }
  });

  // Drag and drop handling
  fileUpload.addEventListener('dragover', function (e) {
    e.preventDefault();
    e.stopPropagation();
    fileUpload.classList.add('dragover');
  });

  fileUpload.addEventListener('dragleave', function (e) {
    e.preventDefault();
    e.stopPropagation();
    fileUpload.classList.remove('dragover');
  });

  fileUpload.addEventListener('drop', function (e) {
    e.preventDefault();
    e.stopPropagation();
    fileUpload.classList.remove('dragover');

    const files = e.dataTransfer.files;
    if (files.length > 0) {
      fileInput.files = files;
      displayFileInfo(files[0]);
      fileSubmitBtn.disabled = false;
    }
  });

  // File form submission
  fileForm.addEventListener('submit', function (e) {
    e.preventDefault();

    const file = fileInput.files[0];
    if (!file) {
      showError('Please select a file to convert.');
      return;
    }

    // Check file size (50MB limit)
    const maxSize = 50 * 1024 * 1024;
    if (file.size > maxSize) {
      showError('File is too large. Maximum size is 50MB.');
      return;
    }

    // Show loading state
    hideError();
    hideResult();
    showLoading();
    fileSubmitBtn.disabled = true;

    // Create FormData and send
    const formData = new FormData();
    formData.append('file', file);

    fetch('/process', {
      method: 'POST',
      body: formData
    })
      .then(response => response.json())
      .then(data => {
        hideLoading();
        fileSubmitBtn.disabled = false;

        if (data.error) {
          showError(data.error);
        } else {
          showResult(data.result, data.filename);
        }
      })
      .catch(error => {
        hideLoading();
        fileSubmitBtn.disabled = false;
        showError('Network error: ' + error.message);
      });
  });

  // Text form handling (existing functionality)
  function updateCharCounter() {
    const length = textArea.value.length;
    const maxLength = 100000;

    charCounter.textContent = `${length.toLocaleString()} / ${maxLength.toLocaleString()} characters`;

    // Update styling based on character count
    charCounter.classList.remove('warning', 'error');
    if (length > maxLength * 0.9) {
      charCounter.classList.add('warning');
    }
    if (length >= maxLength) {
      charCounter.classList.add('error');
    }

    // Disable submit button if text is too long or empty
    const isEmpty = length === 0 || textArea.value.trim().length === 0;
    const isTooLong = length > maxLength;
    textSubmitBtn.disabled = isEmpty || isTooLong;
  }

  // Real-time character counting
  if (textArea) {
    textArea.addEventListener('input', updateCharCounter);
    textArea.addEventListener('paste', function () {
      setTimeout(updateCharCounter, 10);
    });
  }

  // Text form submission
  textForm.addEventListener('submit', function (e) {
    e.preventDefault();

    const inputText = textArea.value.trim();

    // Client-side validation
    if (!inputText) {
      showError('Please enter some text to convert.');
      return;
    }

    if (inputText.length > 100000) {
      showError('Text is too long. Maximum 100,000 characters allowed.');
      return;
    }

    // Show loading state
    hideError();
    hideResult();
    showLoading();
    textSubmitBtn.disabled = true;

    // Send AJAX request
    fetch('/process', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        inputText: inputText
      })
    })
      .then(response => response.json())
      .then(data => {
        hideLoading();
        textSubmitBtn.disabled = false;

        if (data.error) {
          showError(data.error);
        } else {
          showResult(data.result);
        }
      })
      .catch(error => {
        hideLoading();
        textSubmitBtn.disabled = false;
        showError('Network error: ' + error.message);
      });
  });

  // Utility functions
  function displayFileInfo(file) {
    const size = (file.size / (1024 * 1024)).toFixed(2);
    fileInfo.innerHTML = `
      <strong>Selected:</strong> ${file.name} (${size} MB)
      <br><strong>Type:</strong> ${file.type || 'Unknown'}
    `;
    fileInfo.style.display = 'block';
  }

  function hideFileInfo() {
    fileInfo.style.display = 'none';
  }

  function showError(message) {
    errorDiv.textContent = message;
    errorDiv.style.display = 'block';
  }

  function hideError() {
    errorDiv.style.display = 'none';
  }

  function showLoading() {
    loadingDiv.style.display = 'block';
  }

  function hideLoading() {
    loadingDiv.style.display = 'none';
  }

  function showResult(result, filename) {
    const title = filename ? `Conversion Result (${filename}):` : 'Conversion Result:';
    resultDiv.innerHTML = `
      <h3>${title}</h3>
      <pre id="resultContent">${result}</pre>
      <button onclick="downloadMarkdown('${filename || 'converted'}')" style="margin-top: 10px;">Download Markdown</button>
    `;
    resultDiv.style.display = 'block';

    // Scroll to result
    resultDiv.scrollIntoView({
      behavior: 'smooth',
      block: 'start'
    });
  }

  function hideResult() {
    resultDiv.style.display = 'none';
  }

  // Download function
  window.downloadMarkdown = function (filename) {
    const content = document.getElementById('resultContent').textContent;
    const blob = new Blob([content], { type: 'text/markdown' });
    const url = URL.createObjectURL(blob);

    const a = document.createElement('a');
    a.href = url;
    a.download = `${filename}.md`;
    a.click();
    URL.revokeObjectURL(url);
  };

  // Initialize character counter if on text tab
  if (textArea) {
    updateCharCounter();
  }
});
