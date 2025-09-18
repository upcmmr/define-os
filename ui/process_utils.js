/**
 * Process management utilities for Python script execution.
 * Eliminates code duplication and standardizes process handling.
 */

const { spawn } = require('child_process');
const path = require('path');
const config = require('../config');

/**
 * Standard options for Python process spawning
 */
const PYTHON_PROCESS_OPTIONS = {
    cwd: path.join(__dirname, '..'),
    stdio: ['pipe', 'pipe', 'pipe'],
    timeout: config.PYTHON_TIMEOUT_MS
};

/**
 * Execute a Python module with standardized error handling
 * @param {string} module - Python module name (e.g., 'screenshot_urlbox.processor')
 * @param {Array} args - Arguments to pass to the module
 * @param {Object} options - Additional spawn options (optional)
 * @returns {Promise<{output: string, error: string|null}>}
 */
function runPythonModule(module, args = [], options = {}) {
    return new Promise((resolve) => {
        const pythonPath = config.get_python_path();
        const scriptArgs = ['-m', module, ...args];
        
        console.log(`[PROCESS] Running: ${pythonPath} ${scriptArgs.join(' ')}`);
        
        const mergedOptions = { ...PYTHON_PROCESS_OPTIONS, ...options };
        const process = spawn(pythonPath, scriptArgs, mergedOptions);

        let stdout = '';
        let stderr = '';

        process.stdout.on('data', (data) => {
            stdout += data.toString();
        });

        process.stderr.on('data', (data) => {
            stderr += data.toString();
        });

        process.on('close', (code) => {
            if (code === 0) {
                resolve({ output: stdout, error: null });
            } else {
                resolve({ 
                    output: stdout, 
                    error: stderr || `Process exited with code ${code}` 
                });
            }
        });

        process.on('error', (error) => {
            resolve({ output: '', error: error.message });
        });
    });
}

/**
 * Execute a Python script directly with standardized error handling
 * @param {string} scriptPath - Full path to Python script
 * @param {Array} args - Arguments to pass to the script
 * @param {Object} options - Additional spawn options (optional)
 * @returns {Promise<{output: string, error: string|null}>}
 */
function runPythonScript(scriptPath, args = [], options = {}) {
    return new Promise((resolve) => {
        const pythonPath = config.get_python_path();
        
        console.log(`[PROCESS] Running script: ${pythonPath} ${scriptPath} ${args.join(' ')}`);
        
        const mergedOptions = { ...PYTHON_PROCESS_OPTIONS, ...options };
        const process = spawn(pythonPath, [scriptPath, ...args], mergedOptions);

        let stdout = '';
        let stderr = '';

        process.stdout.on('data', (data) => {
            stdout += data.toString();
        });

        process.stderr.on('data', (data) => {
            stderr += data.toString();
        });

        process.on('close', (code) => {
            if (code === 0) {
                resolve({ output: stdout, error: null });
            } else {
                resolve({ 
                    output: stdout, 
                    error: stderr || `Process exited with code ${code}` 
                });
            }
        });

        process.on('error', (error) => {
            resolve({ output: '', error: error.message });
        });
    });
}

/**
 * Parse JSON output from Python process with error handling
 * @param {string} output - Raw stdout from Python process
 * @param {string} context - Context for error messages
 * @returns {Object} Parsed JSON object or error response
 */
function parseProcessOutput(output, context = 'Python process') {
    try {
        return JSON.parse(output);
    } catch (parseError) {
        console.error(`[PROCESS] JSON Parse Error in ${context}:`, parseError.message);
        console.error(`[PROCESS] Raw output (first 500 chars):`, output.substring(0, 500));
        return {
            success: false,
            error: `Failed to parse ${context} response: ${parseError.message}`,
            raw_output: output.substring(0, 200)
        };
    }
}

/**
 * Extract output directory from screenshot process output
 * @param {string} output - Raw stdout from screenshot process
 * @returns {string|null} Extracted directory path or null if not found
 */
function extractOutputDirectory(output) {
    // Try primary pattern
    let match = output.match(/Output saved in: (.+)/);
    if (match) {
        return match[1].trim();
    }
    
    // Try alternative pattern
    match = output.match(/> Output saved in: (.+)/);
    if (match) {
        return match[1].trim();
    }
    
    console.error('[PROCESS] Could not extract output directory from:', output.substring(0, 500));
    return null;
}

/**
 * Extract height information from screenshot process output
 * @param {string} output - Raw stdout from screenshot process
 * @returns {Object} Object with headerHeight and footerHeight properties
 */
function extractHeightInfo(output) {
    const headerMatch = output.match(/Header height: (\d+)/);
    const footerMatch = output.match(/Footer height: (\d+)/);
    
    return {
        headerHeight: headerMatch ? parseInt(headerMatch[1]) : null,
        footerHeight: footerMatch ? parseInt(footerMatch[1]) : null
    };
}

module.exports = {
    runPythonModule,
    runPythonScript,
    parseProcessOutput,
    extractOutputDirectory,
    extractHeightInfo,
    PYTHON_PROCESS_OPTIONS
};
