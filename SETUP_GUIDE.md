# Fashion AI Dashboard - Setup Guide

## Answers to Your Questions

### 1. Trend Combinations Display ✅ FIXED
- **Issue**: Showing all combinations with weight numbers
- **Solution**: Now shows only top 10 combinations without weights
- **Location**: `src/app/page.tsx` lines 270-275

### 2. Trims & Details Parameter Explained

**What it is:**
- "Trims & Details" refers to decorative elements and finishing touches on garments
- Examples: buttons, zippers, lace, embroidery, piping, beads, sequins, etc.
- In fashion design, these are the small details that enhance the aesthetic appeal

**Where it was added:**
- **Frontend**: `src/app/page.tsx` - Line 86 in the design form state
- **Backend API**: `src/app/api/generate-design/route.ts` - Line 26 (converted to `trims_and_details`)
- **Python Script**: `scripts/test_agent2_payload.py` - Line 76 (expected in JSON response)
- **Processing**: The field gets converted from `trims` (frontend) to `trims_and_details` (backend) to match the expected Python script format

**How it works:**
1. User enters trim details in the frontend form
2. API converts it to `trims_and_details` array format
3. Python script includes it in the prompt to Azure OpenAI
4. AI generates designs considering these trim specifications

### 3. Deployment and Running Options

#### Option A: Run Locally (Recommended for Development)
```bash
# 1. Clone the repository
git clone <your-repo-url>
cd fashion-ai-dashboard

# 2. Install dependencies
npm install

# 3. Set up environment variables
cp .env.example .env.local
# Edit .env.local with your actual API keys

# 4. Run the development server
npm run dev

# 5. Open http://localhost:3000
```

#### Option B: Deploy to Vercel (Recommended for Production)
```bash
# 1. Push your code to GitHub
git add .
git commit -m "Initial setup"
git push origin main

# 2. Deploy to Vercel
# - Go to vercel.com
# - Import your GitHub repository
# - Add environment variables in Vercel dashboard
# - Deploy
```

#### Option C: Deploy to Other Platforms
- **Netlify**: Similar to Vercel, connect GitHub repo and add env vars
- **Azure Static Web Apps**: Connect GitHub repo and configure API keys
- **Docker**: Create a Dockerfile and deploy to any cloud platform

#### Integrating Your Backend Files:
1. **Python Scripts**: Already included in `/scripts/` directory
2. **Azure ML Studio**: You can either:
   - Keep scripts in Azure ML and call them via API endpoints
   - Move scripts to this project and run locally (recommended)
   - Set up Azure Functions as middleware

### 4. API Keys Configuration

#### Where to Add API Keys:

**Local Development:**
1. Copy the example file:
   ```bash
   cp .env.example .env.local
   ```

2. Edit `.env.local` with your actual keys:
   ```env
   AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
   AZURE_OPENAI_KEY=your-actual-key-here
   AZURE_OPENAI_DEPLOYMENT=your-deployment-name
   GEMINI_API_KEY=your-gemini-key-here
   ```

**Production Deployment:**
- **Vercel**: Add environment variables in Project Settings → Environment Variables
- **Azure**: Add in Configuration → Application settings
- **Other platforms**: Check their specific environment variable setup

#### How to Get API Keys:

**Azure OpenAI:**
1. Go to Azure Portal
2. Create/Open OpenAI resource
3. Under "Keys and Endpoint", copy:
   - Endpoint URL
   - API Key
   - Deployment name

**Gemini API:**
1. Go to Google AI Studio
2. Create API key
3. Copy the key

#### Environment Variables Used:

**In Python Scripts:**
```python
# scripts/test_agent2_payload.py
AZURE_OPENAI_ENDPOINT = os.environ.get("AZURE_OPENAI_ENDPOINT")
AZURE_OPENAI_KEY = os.environ.get("AZURE_OPENAI_KEY")
AZURE_OPENAI_DEPLOYMENT = os.environ.get("AZURE_OPENAI_DEPLOYMENT")

# scripts/agent3_virtual_showcase_demo.py
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

# scripts/agent3_runway_demo.py
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
```

**In Next.js API Routes:**
Environment variables are automatically available in Next.js API routes when prefixed with `NEXT_PUBLIC_` or accessed through `process.env`.

### 5. Project Structure

```
fashion-ai-dashboard/
├── src/
│   ├── app/
│   │   ├── api/              # API routes
│   │   │   ├── generate-design/
│   │   │   ├── apply-change/
│   │   │   ├── flatlay-render/
│   │   │   ├── virtual-showcase/
│   │   │   ├── runway/
│   │   │   └── trends/
│   │   ├── page.tsx         # Main dashboard
│   │   └── layout.tsx
│   └── components/
├── scripts/                 # Python backend scripts
│   ├── test_agent2_payload.py
│   ├── agent3_virtual_showcase_demo.py
│   ├── agent3_runway_demo.py
│   └── ...
├── trends_index.json        # Trend data
├── .env.example            # Environment variables template
└── package.json
```

### 6. Testing the Application

After setting up:

1. **Test API Endpoints:**
   ```bash
   curl http://localhost:3000/api/trends
   curl http://localhost:3000/api/health
   ```

2. **Test Design Generation:**
   - Open the dashboard
   - Go to "Design Generator" tab
   - Fill in design parameters
   - Click "Generate Design"

3. **Test Virtual Showcase:**
   - Generate a design first
   - Go to "Virtual Showcase" tab
   - Configure model attributes
   - Click "Generate Showcase"

### 7. Troubleshooting

**Common Issues:**

1. **API calls failing:**
   - Check environment variables are set correctly
   - Verify API keys are valid and not expired
   - Check Azure/Gemini service status

2. **Python scripts not running:**
   - Ensure Python 3 is installed
   - Check script permissions: `chmod +x scripts/*.py`
   - Verify required Python packages are installed

3. **Frontend not loading:**
   - Check console for errors
   - Ensure all dependencies are installed
   - Verify API routes are working

**Debug Mode:**
```bash
# Run with debug logging
DEBUG=* npm run dev

# Check API responses
curl -v http://localhost:3000/api/trends
```

### 8. Next Steps

1. **Immediate:**
   - Set up environment variables
   - Test the application locally
   - Verify all API endpoints work

2. **Development:**
   - Customize the UI as needed
   - Add more design parameters
   - Implement user authentication

3. **Production:**
   - Choose deployment platform
   - Set up monitoring
   - Configure error tracking

This setup provides a complete fashion AI dashboard that integrates your existing Python scripts with a modern Next.js frontend.