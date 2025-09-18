const express = require('express');
const { spawn } = require('child_process');
const path = require('path');
const fs = require('fs');

const app = express();
const PORT = 3000;

// Helper function for consistent error responses
function sendError(res, error, statusCode = 500) {
    const errorMessage = error.message || error;
    console.error('API Error:', errorMessage);
    res.status(statusCode).json({
        success: false,
        error: errorMessage
    });
}

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

// Discover links endpoint (Phase 1)
app.post('/discover-links', async (req, res) => {
    const { url } = req.body;
    
    if (!url) {
        return sendError(res, 'URL is required', 400);
    }

    try {
        console.log(`Discovering links for URL: ${url}`);
        
        // Step 1: Run screenshot capture with slicing
        console.log('Step 1: Capturing screenshots and slicing...');
        const screenshotResult = await runPythonScript('screenshot_urlbox.processor', [url]);
        
        if (screenshotResult.error) {
            throw new Error(`Screenshot failed: ${screenshotResult.error}`);
        }

        // Extract output directory from screenshot result
        console.log('Screenshot output:', screenshotResult.output);
        const outputDirMatch = screenshotResult.output.match(/Output saved in: (.+)/);
        let outputDir;
        if (!outputDirMatch) {
            const altMatch = screenshotResult.output.match(/> Output saved in: (.+)/);
            if (!altMatch) {
                console.error('Full screenshot output:', screenshotResult.output);
                throw new Error(`Could not find output directory from screenshot result. Output: ${screenshotResult.output.substring(0, 500)}`);
            }
            outputDir = altMatch[1].trim();
        } else {
            outputDir = outputDirMatch[1].trim();
        }
        
        const outputDirName = path.basename(outputDir);
        console.log(`Screenshots saved to: ${outputDirName}`);

        // Step 2: Extract slice heights from the processor output
        let headerHeight = null;
        let footerHeight = null;
        
        // Look for height information in the output
        const headerHeightMatch = screenshotResult.output.match(/Header height: (\d+)/);
        const footerHeightMatch = screenshotResult.output.match(/Footer height: (\d+)/);
        
        if (headerHeightMatch) headerHeight = parseInt(headerHeightMatch[1]);
        if (footerHeightMatch) footerHeight = parseInt(footerHeightMatch[1]);

        // Step 3: Run link analysis only
        console.log('Step 2: Extracting links...');
        const headerImagePath = path.join(outputDir, 'header.png');
        const footerImagePath = path.join(outputDir, 'footer.png');
        const headerHtmlPath = path.join(outputDir, 'header.html');
        const footerHtmlPath = path.join(outputDir, 'footer.html');
        
        // Check if required files exist
        const hasHeader = fs.existsSync(headerImagePath) && fs.existsSync(headerHtmlPath);
        const hasFooter = fs.existsSync(footerImagePath) && fs.existsSync(footerHtmlPath);
        
        console.log(`File check - Header: ${hasHeader} (img: ${fs.existsSync(headerImagePath)}, html: ${fs.existsSync(headerHtmlPath)})`);
        console.log(`File check - Footer: ${hasFooter} (img: ${fs.existsSync(footerImagePath)}, html: ${fs.existsSync(footerHtmlPath)})`);
        
        let linksResult = null;
        if (hasHeader && hasFooter) {
            console.log('Running site links analyzer...');
            // Use the command line interface of the site_links_analyzer
            const pythonPath = path.join(__dirname, '..', 'venv2', 'Scripts', 'python.exe');
            const scriptPath = path.join(__dirname, '..', 'ai_analysis', 'site_links_analyzer.py');
            
            console.log('Running site links analyzer with paths:');
            console.log('  Python:', pythonPath);
            console.log('  Script:', scriptPath);
            console.log('  Args:', [headerImagePath, headerHtmlPath, footerImagePath, footerHtmlPath, url]);
            
            const linksAnalysis = await new Promise((resolve) => {
                const { spawn } = require('child_process');
                const process = spawn(pythonPath, [scriptPath, headerImagePath, headerHtmlPath, footerImagePath, footerHtmlPath, url], {
                    cwd: path.join(__dirname, '..'),
                    stdio: ['pipe', 'pipe', 'pipe'],
                    timeout: 300000
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
            
            console.log('Links analysis completed. Error:', linksAnalysis.error ? 'YES' : 'NO');
            if (linksAnalysis.error) {
                console.error('Links analysis error:', linksAnalysis.error);
                console.log('Links analysis stdout:', linksAnalysis.output.substring(0, 500));
            }
            
            if (!linksAnalysis.error) {
                try {
                    linksResult = JSON.parse(linksAnalysis.output);
                    console.log('Successfully parsed links result. Links found:', linksResult.links ? linksResult.links.length : 0);
                } catch (parseError) {
                    console.error('Failed to parse links analysis:', parseError.message);
                    console.log('Raw output (first 500 chars):', linksAnalysis.output.substring(0, 500));
                }
            }
        } else {
            console.log('Skipping link analysis - missing required files');
        }

        // Step 4: Prepare response
        const response = {
            success: true,
            outputDir: outputDirName,
            images: {
                header: `/screenshots/${outputDirName}/header.png`,
                body: `/screenshots/${outputDirName}/body.png`,
                footer: `/screenshots/${outputDirName}/footer.png`
            },
            sliceHeights: {
                header: headerHeight,
                footer: footerHeight
            },
            links: linksResult || { success: false, error: 'Link extraction failed' },
            url: url
        };

        if (linksResult && linksResult.success) {
            console.log('Link discovery completed successfully');
        } else {
            console.log('Link discovery completed with errors - links extraction failed');
        }
        res.json(response);

    } catch (error) {
        sendError(res, error);
    }
});

// Process URL endpoint (Legacy - keeping for backward compatibility)
app.post('/process', async (req, res) => {
    const { url } = req.body;
    
    if (!url) {
        return sendError(res, 'URL is required', 400);
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
        let outputDir;
        if (!outputDirMatch) {
            // Try alternative pattern
            const altMatch = screenshotResult.output.match(/> Output saved in: (.+)/);
            if (!altMatch) {
                console.error('Full screenshot output:', screenshotResult.output);
                throw new Error(`Could not find output directory from screenshot result. Output: ${screenshotResult.output.substring(0, 500)}`);
            }
            outputDir = altMatch[1].trim();
        } else {
            outputDir = outputDirMatch[1].trim();
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
            siteLinksAnalysis: aiResult.analysis?.results?.sitelinks || null,
            url: url
        };

        console.log('Processing completed successfully');
        res.json(response);

    } catch (error) {
        sendError(res, error);
    }
});

// Start analysis job endpoint (Phase 2)
app.post('/start-analysis', async (req, res) => {
    const { urls, headerHeight, footerHeight } = req.body;
    
    if (!urls || !Array.isArray(urls) || urls.length === 0) {
        return sendError(res, 'URLs array is required', 400);
    }

    try {
        // Generate unique job ID
        const jobId = Date.now().toString() + '_' + Math.random().toString(36).substring(2, 11);
        
        // Store job info in memory (in production, use Redis or database)
        if (!global.analysisJobs) {
            global.analysisJobs = {};
        }
        
        global.analysisJobs[jobId] = {
            urls: urls,
            headerHeight: headerHeight,
            footerHeight: footerHeight,
            status: 'started',
            completed: [],
            total: urls.length,
            startTime: Date.now()
        };

        console.log(`Started analysis job ${jobId} for ${urls.length} URLs`);
        
        // Start processing in background
        console.log(`Starting background processing for job ${jobId}`);
        processAnalysisJob(jobId);
        
        res.json({
            success: true,
            jobId: jobId,
            totalPages: urls.length
        });

    } catch (error) {
        sendError(res, error);
    }
});

// Server-Sent Events endpoint for streaming analysis results
app.get('/analysis-stream/:jobId', (req, res) => {
    const jobId = req.params.jobId;
    
    if (!global.analysisJobs || !global.analysisJobs[jobId]) {
        return sendError(res, 'Job not found', 404);
    }

    // Set up SSE headers
    res.writeHead(200, {
        'Content-Type': 'text/event-stream',
        'Cache-Control': 'no-cache',
        'Connection': 'keep-alive',
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Headers': 'Cache-Control'
    });

    const job = global.analysisJobs[jobId];
    
    // Store this connection for broadcasting
    if (!job.sseConnections) {
        job.sseConnections = [];
    }
    job.sseConnections.push(res);
    
    // Send initial status
    res.write(`data: ${JSON.stringify({
        type: 'started',
        jobId: jobId,
        totalPages: job.total,
        completed: job.completed.length
    })}\n\n`);

    // Send any already completed results
    job.completed.forEach(result => {
        res.write(`data: ${JSON.stringify({
            type: 'page-complete',
            ...result
        })}\n\n`);
    });

    // Handle client disconnect
    req.on('close', () => {
        if (job.sseConnections) {
            const index = job.sseConnections.indexOf(res);
            if (index > -1) {
                job.sseConnections.splice(index, 1);
            }
        }
    });
    
    // If job is already finished, send finish event
    if (job.status === 'finished') {
        res.write(`data: ${JSON.stringify({
            type: 'finished',
            jobId: jobId,
            totalCompleted: job.completed.length,
            duration: Date.now() - job.startTime
        })}\n\n`);
        res.end();
    }
});

// Function to determine if a URL is the homepage
function isHomePageUrl(url, allUrls) {
    try {
        const urlObj = new URL(url);
        const pathname = urlObj.pathname;
        
        // Check if it's root path or common homepage patterns
        if (pathname === '/' || pathname === '' || pathname === '/index.html' || pathname === '/home') {
            return true;
        }
        
        // If we have multiple URLs, find the one that looks most like a homepage
        if (allUrls && allUrls.length > 1) {
            const homePatterns = ['/', '/index.html', '/home', '/index.php'];
            for (const pattern of homePatterns) {
                const homeUrl = new URL(pattern, urlObj.origin).href;
                if (url === homeUrl) {
                    return true;
                }
            }
            
            // If no clear homepage pattern, consider the first URL in the list as homepage
            return url === allUrls[0];
        }
        
        return false;
    } catch (error) {
        console.error('Error determining homepage:', error.message);
        return false;
    }
}

// Function to broadcast events to all SSE connections for a job
function broadcastToJob(jobId, eventData) {
    const job = global.analysisJobs[jobId];
    if (!job || !job.sseConnections) return;
    
    const message = `data: ${JSON.stringify(eventData)}\n\n`;
    
    // Send to all connected clients
    job.sseConnections.forEach((res, index) => {
        try {
            res.write(message);
        } catch (error) {
            console.error('Error writing to SSE connection:', error.message);
            // Remove broken connection
            job.sseConnections.splice(index, 1);
        }
    });
}

// Background job processing function
async function processAnalysisJob(jobId) {
    const job = global.analysisJobs[jobId];
    if (!job) return;

    console.log(`Processing analysis job ${jobId} with ${job.urls.length} URLs`);

    for (let i = 0; i < job.urls.length; i++) {
        const url = job.urls[i];
        
        try {
            console.log(`Processing URL ${i + 1}/${job.urls.length}: ${url}`);
            
            // Run screenshot capture with predefined heights
            const screenshotArgs = [url];
            if (job.headerHeight) screenshotArgs.push('--header-height', job.headerHeight.toString());
            if (job.footerHeight) screenshotArgs.push('--footer-height', job.footerHeight.toString());
            
            const screenshotResult = await runPythonScript('screenshot_urlbox.processor', screenshotArgs);
            
            if (screenshotResult.error) {
                throw new Error(`Screenshot failed: ${screenshotResult.error}`);
            }

            // Extract output directory
            const outputDirMatch = screenshotResult.output.match(/Output saved in: (.+)/) || 
                                 screenshotResult.output.match(/> Output saved in: (.+)/);
            
            if (!outputDirMatch) {
                throw new Error('Could not find output directory');
            }
            
            const outputDir = outputDirMatch[1].trim();
            const outputDirName = path.basename(outputDir);

            // Determine analysis type based on whether this is the homepage
            const isHomepage = isHomePageUrl(url, job.urls);
            const analysisType = isHomepage ? 'all' : 'body';
            
            console.log(`Running ${analysisType} analysis for ${url} (homepage: ${isHomepage})`);
            
            // Run AI analysis
            const aiResult = await runAIAnalysis(outputDir, url, analysisType);
            
            if (aiResult.error) {
                throw new Error(`AI analysis failed: ${aiResult.error}`);
            }

            // Prepare result based on analysis type
            const result = {
                url: url,
                success: true,
                outputDir: outputDirName,
                analysisType: analysisType,
                images: {
                    body: `/screenshots/${outputDirName}/body.png`
                },
                bodyAnalysis: aiResult.analysis?.results?.body || null
            };
            
            // Add header/footer data only for homepage (full analysis)
            if (analysisType === 'all') {
                result.images.header = `/screenshots/${outputDirName}/header.png`;
                result.images.footer = `/screenshots/${outputDirName}/footer.png`;
                result.headerAnalysis = aiResult.analysis?.results?.header || null;
                result.footerAnalysis = aiResult.analysis?.results?.footer || null;
                result.siteLinksAnalysis = aiResult.analysis?.results?.sitelinks || null;
            }

            // Add to completed results
            job.completed.push(result);
            
            // Broadcast page completion immediately
            broadcastToJob(jobId, {
                type: 'page-complete',
                ...result
            });
            
            console.log(`Completed analysis for ${url} (${job.completed.length}/${job.total})`);

        } catch (error) {
            console.error(`Error processing ${url}:`, error.message);
            
            // Add error result
            const errorResult = {
                url: url,
                success: false,
                error: error.message
            };
            job.completed.push(errorResult);
            
            // Broadcast error result immediately
            broadcastToJob(jobId, {
                type: 'page-complete',
                ...errorResult
            });
        }
    }

    // Mark job as finished
    job.status = 'finished';
    
    // Broadcast completion to all connected clients
    broadcastToJob(jobId, {
        type: 'finished',
        jobId: jobId,
        totalCompleted: job.completed.length,
        duration: Date.now() - job.startTime
    });
    
    // Close all SSE connections
    if (job.sseConnections) {
        job.sseConnections.forEach(res => {
            try {
                res.end();
            } catch (error) {
                console.error('Error closing SSE connection:', error.message);
            }
        });
        job.sseConnections = [];
    }
    
    console.log(`Analysis job ${jobId} completed. Processed ${job.completed.length}/${job.total} URLs`);
}

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
async function runAIAnalysis(outputDir, url, analysisType = 'all') {
    try {
        const headerImagePath = path.join(outputDir, 'header.png');
        const footerImagePath = path.join(outputDir, 'footer.png');
        const headerHtmlPath = path.join(outputDir, 'header.html');
        const footerHtmlPath = path.join(outputDir, 'footer.html');
        
        // Check if required files exist based on analysis type
        const bodyImagePath = path.join(outputDir, 'body.png');
        const bodyHtmlPath = path.join(outputDir, 'body.html');
        
        const hasHeader = fs.existsSync(headerImagePath) && fs.existsSync(headerHtmlPath);
        const hasFooter = fs.existsSync(footerImagePath) && fs.existsSync(footerHtmlPath);
        const hasBody = fs.existsSync(bodyImagePath) && fs.existsSync(bodyHtmlPath);
        
        // Validate required files based on analysis type
        if (analysisType === 'all') {
        if (!hasHeader && !hasFooter) {
                throw new Error('No header or footer files found for full analysis');
            }
        } else if (analysisType === 'body') {
            if (!hasBody) {
                throw new Error('No body files found for body analysis');
            }
        }

        // Run comprehensive AI analysis Python script
        const aiScriptPath = path.join(__dirname, 'middleware.py');
        const pythonPath = path.join(__dirname, '..', 'venv2', 'Scripts', 'python.exe');
        
        console.log(`Running AI analysis with type: ${analysisType}`);
        const process = spawn(pythonPath, [aiScriptPath, outputDir, url, analysisType], {
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
