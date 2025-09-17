const express = require('express');
const { spawn } = require('child_process');
const path = require('path');
const fs = require('fs');

const app = express();
const PORT = 3000;

// Middleware
app.use(express.json());
app.use(express.urlencoded({ extended: true }));
app.use(express.static('public'));

// Serve static files from screenshot outputs
app.use('/screenshots', express.static(path.join(__dirname, '..', 'screenshot_urlbox', 'output')));

// Home route
app.get('/', (req, res) => {
    res.sendFile(path.join(__dirname, 'public', 'index.html'));
});

// Process URL endpoint
app.post('/process', async (req, res) => {
    const { url } = req.body;
    
    if (!url) {
        return res.status(400).json({ error: 'URL is required' });
    }

    try {
        console.log(`Processing URL: ${url}`);
        
        // Step 1: Run screenshot capture
        console.log('Step 1: Capturing screenshots...');
        const screenshotResult = await runPythonScript('screenshot_urlbox.processor', [url]);
        
        if (screenshotResult.error) {
            throw new Error(`Screenshot failed: ${screenshotResult.error}`);
        }

        // Extract output directory from screenshot result
        console.log('Screenshot output:', screenshotResult.output);
        const outputDirMatch = screenshotResult.output.match(/Output saved in: (.+)/);
        if (!outputDirMatch) {
            // Try alternative pattern
            const altMatch = screenshotResult.output.match(/> Output saved in: (.+)/);
            if (!altMatch) {
                console.error('Full screenshot output:', screenshotResult.output);
                throw new Error(`Could not find output directory from screenshot result. Output: ${screenshotResult.output.substring(0, 500)}`);
            }
            var outputDir = altMatch[1].trim();
        } else {
            var outputDir = outputDirMatch[1].trim();
        }
        
        const outputDirName = path.basename(outputDir);
        
        console.log(`Screenshots saved to: ${outputDirName}`);

        // Step 2: Run AI analysis
        console.log('Step 2: Running AI analysis...');
        const aiResult = await runAIAnalysis(outputDir, url);
        
        if (aiResult.error) {
            throw new Error(`AI analysis failed: ${aiResult.error}`);
        }

        // Step 3: Prepare response with file paths
        const response = {
            success: true,
            outputDir: outputDirName,
            images: {
                full: `/screenshots/${outputDirName}/full_page.png`,
                header: `/screenshots/${outputDirName}/header.png`,
                footer: `/screenshots/${outputDirName}/footer.png`,
                body: `/screenshots/${outputDirName}/body.png`
            },
            headerAnalysis: aiResult.analysis?.results?.header || null,
            footerAnalysis: aiResult.analysis?.results?.footer || null,
            bodyAnalysis: aiResult.analysis?.results?.body || null,
            url: url
        };

        console.log('Processing completed successfully');
        res.json(response);

    } catch (error) {
        console.error('Processing error:', error.message);
        res.status(500).json({ 
            error: error.message,
            success: false 
        });
    }
});

// Helper function to run Python scripts
function runPythonScript(module, args = []) {
    return new Promise((resolve, reject) => {
        const pythonPath = path.join(__dirname, '..', 'venv2', 'Scripts', 'python.exe');
        const scriptArgs = ['-m', module, ...args];
        
        console.log(`Running: ${pythonPath} ${scriptArgs.join(' ')}`);
        
        const process = spawn(pythonPath, scriptArgs, {
            cwd: path.join(__dirname, '..'),
            stdio: ['pipe', 'pipe', 'pipe'],
            timeout: 300000  // 5 minute timeout for Python processes
        });

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
                resolve({ output: stdout, error: stderr || `Process exited with code ${code}` });
            }
        });

        process.on('error', (error) => {
            resolve({ output: '', error: error.message });
        });
    });
}

// Helper function to run AI analysis
async function runAIAnalysis(outputDir, url) {
    try {
        const headerImagePath = path.join(outputDir, 'header.png');
        const footerImagePath = path.join(outputDir, 'footer.png');
        const headerHtmlPath = path.join(outputDir, 'header.html');
        const footerHtmlPath = path.join(outputDir, 'footer.html');
        
        // Check if required files exist
        const hasHeader = fs.existsSync(headerImagePath) && fs.existsSync(headerHtmlPath);
        const hasFooter = fs.existsSync(footerImagePath) && fs.existsSync(footerHtmlPath);
        
        if (!hasHeader && !hasFooter) {
            throw new Error('No header or footer files found for AI analysis');
        }

        // Run comprehensive AI analysis Python script
        const aiScriptPath = path.join(__dirname, 'middleware.py');
        const pythonPath = path.join(__dirname, '..', 'venv2', 'Scripts', 'python.exe');
        
        const process = spawn(pythonPath, [aiScriptPath, outputDir, url, 'all'], {
            cwd: __dirname,
            stdio: ['pipe', 'pipe', 'pipe']
        });

        let stdout = '';
        let stderr = '';

        process.stdout.on('data', (data) => {
            stdout += data.toString();
        });

        process.stderr.on('data', (data) => {
            stderr += data.toString();
        });

        return new Promise((resolve, reject) => {
            process.on('close', (code) => {
                if (code === 0) {
                    try {
                        console.log('AI Analysis stdout:', stdout.substring(0, 200) + '...');
                        const analysis = JSON.parse(stdout);
                        
                        // Check if the analysis itself indicates an error
                        if (analysis.success === false) {
                            console.error('AI Analysis Error:', analysis.error);
                            resolve({ analysis: null, error: analysis.error || 'AI analysis returned error' });
                        } else {
                            resolve({ analysis, error: null });
                        }
                    } catch (parseError) {
                        console.error('JSON Parse Error:', parseError.message);
                        console.error('Raw stdout:', stdout.substring(0, 500));
                        resolve({ analysis: null, error: `Failed to parse AI response: ${parseError.message}. Raw output: ${stdout.substring(0, 200)}` });
                    }
                } else {
                    resolve({ analysis: null, error: stderr || `AI analysis failed with code ${code}` });
                }
            });

            process.on('error', (error) => {
                resolve({ analysis: null, error: error.message });
            });
        });

    } catch (error) {
        return { analysis: null, error: error.message };
    }
}

app.listen(PORT, () => {
    console.log(`Server running at http://localhost:${PORT}`);
});
