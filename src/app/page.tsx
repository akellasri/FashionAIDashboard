"use client";

import { useState, useEffect } from 'react'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Separator } from '@/components/ui/separator'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Progress } from '@/components/ui/progress'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Palette, Shirt, Zap, TrendingUp, Download, Play, Eye } from 'lucide-react'

// Separate APIs
const PY_BACKEND = (process.env.NEXT_PUBLIC_API_BASE_URL || "").replace(/\/$/, "");
//const NEXT_API = "/api"; // still used to try Next.js routes first (optional)
const API_BASE = PY_BACKEND; // unify any old uses

export default function FashionAIDashboard() {
  const [activeTab, setActiveTab] = useState('trends')
  const [selectedDesign, setSelectedDesign] = useState(null)
  const [isGenerating, setIsGenerating] = useState(false)
  const [generationProgress, setGenerationProgress] = useState(0)
  const [trendData, setTrendData] = useState(null)
  const [loading, setLoading] = useState(true) // Start with loading = true


  // helper: fetch with timeout
  const fetchWithTimeout = async (url: string, opts = {}, ms = 10000) => {
    const controller = new AbortController();
    const id = setTimeout(() => controller.abort(), ms);
    try {
      const res = await fetch(url, {
        signal: controller.signal,
        ...opts,
      });
      clearTimeout(id);
      return res;
    } catch (err) {
      clearTimeout(id);
      throw err;
    }
  };

  // ✅ Direct backend fetch for trends
  useEffect(() => {
    const loadData = async () => {
      console.log('Fetching trends from backend:', `${PY_BACKEND}/trends`);
      try {
        const response = await fetchWithTimeout(`${PY_BACKEND}/trends`, {}, 15000);
        if (!response.ok) throw new Error(`Backend responded with ${response.status}`);
        const data = await response.json();
        setTrendData(data);
      } catch (error) {
        console.error('Error fetching trend data:', error);
        // fallback sample data
        setTrendData({
          top_by_category: {
            colors: [
              "brown",
              "white",
              "grey",
              "cream",
              "black",
              "red",
              "olive",
              "beige",
              "blue",
              "pink",
            ],
            fabrics: [
              "cotton",
              "silk",
              "linen",
              "satin",
              "chiffon",
              "lace",
              "denim",
              "rayon",
              "chikankari",
              "crepe",
            ],
            prints: [
              "embroidery",
              "solids / minimalist",
              "florals",
              "bandhani",
              "ikat",
              "block print",
              "geometric",
              "paisley",
              "polka dot",
              "floral",
            ],
            silhouettes: [
              "Draped/Flowing",
              "A-line",
              "Tailored",
              "Fit-and-flare",
              "sheath",
              "Bodycon/Fitted",
              "anarkali",
              "Oversized/Baggy",
              "slip dress",
              "asymmetric",
            ],
            sleeves: [
              "Full sleeves",
              "Sleeveless/Tank",
              "short sleeve",
              "3/4th sleeves",
              "kimono sleeve",
              "bell sleeve",
            ],
            necklines: [
              "Crew neck",
              "V-neck",
              "Collared",
              "Halter",
              "Square neck",
              "Sweetheart neck",
              "Off-shoulder",
              "Asymmetrical/One-shoulder",
              "Cowl neck",
            ],
            garment_types: [
              "dress",
              "kurta",
              "kurta-set",
              "coord set",
              "top",
              "shirt",
              "lehenga",
              "sari",
              "jacket",
              "skirt",
            ],
            lengths: [
              "Full-length",
              "Midi",
              "Mini",
              "Ankle-length",
              "Maxi",
              "Cropped",
              "Knee-length",
            ],
          },
          top_combos: [
            { combo: 'color:brown | color:white', weight: 329 },
            { combo: 'color:grey | color:white', weight: 260 },
            { combo: "color:white | garment:dress", weight: 240 },
            { combo: "color:white | print:solids / minimalist", weight: 239 },
            { combo: "color:red | color:white", weight: 199 },
          ],
          trend_entries: [
            {
              trend_id: "fabric:cotton",
              type: "fabric",
              canonical: "cotton",
              count: 282,
              score: 1.18,
            },
            {
              trend_id: "print:embroidery",
              type: "print",
              canonical: "embroidery",
              count: 285,
              score: 1.12,
            },
            {
              trend_id: "print:solids / minimalist",
              type: "print",
              canonical: "solids / minimalist",
              count: 397,
              score: 1.11,
            },
            {
              trend_id: "color:brown",
              type: "color",
              canonical: "brown",
              count: 580,
              score: 1.09,
            },
            {
              trend_id: "color:white",
              type: "color",
              canonical: "white",
              count: 804,
              score: 1.05,
            },
          ],
        });
      } finally {
        setLoading(false);
      }
    };

    loadData();
  }, []);


  // Model customization state
  const [modelConfig, setModelConfig] = useState({
    gender: 'female',
    bodyType: 'athletic',
    skinTone: 'medium',
    pose: 'walk'
  })

  // Design form state (added per-category description fields)
  const [designForm, setDesignForm] = useState({
    colors: [],
    fabrics: [],
    prints: [],
    garmentType: '',
    silhouette: '',
    sleeves: '',
    neckline: '',
    // remove trims field from pipeline; use descriptions instead
    descriptions: ''
  })

  const [generatedDesign, setGeneratedDesign] = useState(null)
  const [currentDesign, setCurrentDesign] = useState<any | null>(null)
  const [flatlayUrl, setFlatlayUrl] = useState<string | null>(null)
  const [flatlayLocalPath, setFlatlayLocalPath] = useState<string | null>(null);
  const [showcaseUrl, setShowcaseUrl] = useState<string | null>(null)
  const [runwayUrl, setRunwayUrl] = useState<string | null>(null)
  // state for edit box + apply-change flow
  const [editText, setEditText] = useState<string>("");
  const [applyingChange, setApplyingChange] = useState(false);



  // -----------------------
  // Generate Design + Flatlay
  // -----------------------
  const handleGenerateDesign = async () => {
    setIsGenerating(true);
    setGenerationProgress(0);

    try {
      const genResp = await fetch(`${API_BASE || ""}/generate-design`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(designForm),
      });
      const genResult = await genResp.json();

      if (!(genResp.ok && genResult.success && genResult.design)) {
        alert("Design generation failed");
        return;
      }

      const design = genResult.design;
      setGeneratedDesign(design);
      setCurrentDesign(design);

      // request flatlay
      setFlatlayUrl(null);
      const flatResp = await fetch(`${PY_BACKEND}/flatlay-render`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ design }),
      });
      const flatResult = await flatResp.json();

      if (flatResp.ok && flatResult.success) {
        const assets = toAssetsUrl(
          flatResult.imageUrl || flatResult.savedPath || flatResult.saved_path
        );
        setFlatlayUrl(withCacheBuster(assets));
        if (flatResult.localPath) setFlatlayLocalPath(flatResult.localPath);

        console.log("Flatlay generated:", assets, flatResult.localPath);
      } else {
        alert("Flatlay failed");
      }
    } catch (err: any) {
      alert("Error: " + (err?.message || String(err)));
    } finally {
      setIsGenerating(false);
      setGenerationProgress(100);
    }
  };


  // -----------------------
  // Render Flatlay manually
  // -----------------------
  async function handleRenderFlatlay() {
    if (!currentDesign) {
      alert("Please generate or select a design first.");
      return;
    }

    try {
      setFlatlayUrl(null);
      const res = await fetch(`${PY_BACKEND}/flatlay-render`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ design: currentDesign }),
      });
      const result = await res.json();

      if (result?.success) {
        const assets = toAssetsUrl(
          result.imageUrl || result.savedPath || result.saved_path
        );
        setFlatlayUrl(withCacheBuster(assets));
        if (result.localPath) setFlatlayLocalPath(result.localPath);

        console.log("Flatlay regenerated:", assets, result.localPath);
      } else {
        alert("Flatlay generation failed");
      }
    } catch (err: any) {
      alert("Flatlay generation error: " + err.message);
    }
  }

  // -----------------------
  // Virtual Showcase
  // -----------------------
  async function handleVirtualShowcase(modelConfig: any) {
    if (!currentDesign) {
      alert("Please generate or select a design first.");
      return;
    }

    try {
      setShowcaseUrl(null);

      // Prefer localPath if available
      const referenceUrl = flatlayLocalPath || toAbsoluteUrl(flatlayUrl);

      const normalized = normalizeModelConfigForBackend(modelConfig);
      const body = {
        design: currentDesign,
        modelConfig: normalized,
        ...(referenceUrl ? { reference: referenceUrl } : {}),
      };

      const res = await fetch(`${PY_BACKEND}/virtual-showcase`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });

      const result = await res.json();

      if (result?.success) {
        const assets = toAssetsUrl(
          result.imageUrl || result.savedPath || result.saved_path
        );
        setShowcaseUrl(assets ? withCacheBuster(assets) ?? assets : null);
        console.log("Virtual showcase generated:", assets);
      } else {
        alert("Virtual showcase failed");
      }
    } catch (err: any) {
      alert("Virtual showcase error: " + err.message);
    }
  }


  // -----------------------
  // Runway
  // -----------------------
  async function handleRunway(modelConfig: any) {
    if (!currentDesign) {
      alert("Please generate or select a design first.");
      return;
    }

    try {
      setRunwayUrl(null);

      const referenceUrl = flatlayLocalPath || toAbsoluteUrl(flatlayUrl);

      const normalized = normalizeModelConfigForBackend(modelConfig);
      const body = {
        design: currentDesign,
        modelConfig: normalized,
        ...(referenceUrl ? { reference: referenceUrl } : {}),
      };

      const res = await fetch(`${PY_BACKEND}/runway`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });

      const result = await res.json();

      if (result?.success) {
        const assets = toAssetsUrl(
          result.videoUrl || result.savedPath || result.video_path
        );
        setRunwayUrl(assets ? withCacheBuster(assets) ?? assets : null);
        console.log("Runway generated:", assets);
      } else {
        alert("Runway generation failed");
      }
    } catch (err: any) {
      alert("Runway error: " + err.message);
    }
  }

  // -----------------------
  // Apply Change
  // -----------------------
  async function handleApplyChange() {
    if (!currentDesign) {
      alert("Please generate or select a design first.");
      return;
    }
    if (!editText || editText.trim().length === 0) {
      alert("Please enter a change description before applying.");
      return;
    }

    try {
      setApplyingChange(true);
      const body = { design: currentDesign, textChange: editText.trim() };

      const url = `${PY_BACKEND}/apply-change`;
      const res = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const result = await res.json();

      if (!res.ok || !result.success) {
        alert("Apply change failed");
        return;
      }

      const updated = result.design;
      setGeneratedDesign(updated);
      setCurrentDesign(updated);
      setEditText(updated.design_text || "");
      alert("Design updated successfully.");
    } catch (err: any) {
      alert("Error applying change: " + err.message);
    } finally {
      setApplyingChange(false);
    }
  }


  // Convert backend returned path into a full asset URL for the browser
  const toAssetsUrl = (backendPath?: string | null): string | null => {
    if (!backendPath) return null;
    if (/^https?:\/\//i.test(backendPath)) return backendPath;

    const normalized = backendPath.replace(/\\/g, "/").trim();

    if (normalized.startsWith("/api/assets") || normalized.startsWith("/assets")) {
      return normalized;
    }

    const allowedPrefixes = ["renders/", "output/", "temp/", "public/"];
    for (const pref of allowedPrefixes) {
      const idx = normalized.indexOf(pref);
      if (idx !== -1) {
        const rel = normalized.slice(idx).replace(/^\/+/, "");
        return API_BASE ? `${API_BASE}/assets/${encodeURIComponent(rel)}` : `/assets/${encodeURIComponent(rel)}`;
      }
    }

    return API_BASE ? `${API_BASE}/${normalized.replace(/^\/+/, "")}` : `/${normalized.replace(/^\/+/, "")}`;
  };

  const withCacheBuster = (url?: string | null): string | null =>
    url ? (url.includes("?") ? `${url}&t=${Date.now()}` : `${url}?t=${Date.now()}`) : null;

  const toAbsoluteUrl = (rel?: string | null) => {
    if (!rel) return null;
    if (rel.startsWith("http://") || rel.startsWith("https://")) return rel;
    return `${window.location.origin}${rel.startsWith("/") ? "" : "/"}${rel}`;
  };


  // Map frontend modelConfig keys to backend/Python expected keys
  function normalizeModelConfigForBackend(m: any) {
    if (!m) return {}
    return {
      gender: m.gender || m?.gender,
      age_range: m.ageRange || m?.age_range || "25-32",
      body_type: m.bodyType || m.body_type || "slim",
      skin_tone: m.skinTone || m.skin_tone || "medium",
      pose: m.pose || "standing",
      framing: m.framing || "full-body, studio frame, no close-ups",
    }
  }


  return (
    <div className="min-h-screen bg-gradient-to-br from-purple-50 via-pink-50 to-blue-50 p-4">
      <div className="max-w-7xl mx-auto">
        {/* Header */}
        <div className="mb-8 text-center">
          <h1 className="text-4xl font-bold bg-gradient-to-r from-purple-600 to-pink-600 bg-clip-text text-transparent mb-2">
            Fashion AI Dashboard
          </h1>
          <p className="text-gray-600 text-lg">Trend Insights • Design Generation • Virtual Showcase</p>
        </div>

        <Tabs value={activeTab} onValueChange={setActiveTab} className="space-y-6">
          <TabsList className="grid w-full grid-cols-3 max-w-2xl mx-auto">
            <TabsTrigger value="trends" className="flex items-center gap-2">
              <TrendingUp className="w-4 h-4" />
              Trend Insights
            </TabsTrigger>
            <TabsTrigger value="design" className="flex items-center gap-2">
              <Palette className="w-4 h-4" />
              Design Generator
            </TabsTrigger>
            <TabsTrigger value="showcase" className="flex items-center gap-2">
              <Shirt className="w-4 h-4" />
              Virtual Showcase
            </TabsTrigger>
          </TabsList>

          {/* Agent 1 - Trend Insights */}
          <TabsContent value="trends" className="space-y-6">
            {loading ? (
              <div className="text-center py-8">
                <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-purple-600 mx-auto mb-4"></div>
                <p className="text-gray-600">Loading trend data...</p>
              </div>
            ) : trendData ? (
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                {/* Top Categories */}
                <Card className="bg-white/80 backdrop-blur-sm border-0 shadow-lg">
                  <CardHeader>
                    <CardTitle className="flex items-center gap-2 text-purple-700">
                      <TrendingUp className="w-5 h-5" />
                      Top Categories
                    </CardTitle>
                    <CardDescription>Trending fashion categories</CardDescription>
                  </CardHeader>
                  <CardContent className="space-y-4">
                    {Object.entries(trendData.top_by_category).map(([category, items]) => (
                      <div key={category} className="space-y-2">
                        <h3 className="font-semibold text-gray-700 capitalize">{category}</h3>
                        <div className="flex flex-wrap gap-2">
                          {items.slice(0, 5).map((item, index) => (
                            <Badge key={index} variant="secondary" className="text-xs">
                              {item}
                            </Badge>
                          ))}
                        </div>
                      </div>
                    ))}
                  </CardContent>
                </Card>

                {/* Top Combos Chart */}
                <Card className="bg-white/80 backdrop-blur-sm border-0 shadow-lg">
                  <CardHeader>
                    <CardTitle className="flex items-center gap-2 text-pink-700">
                      <Zap className="w-5 h-5" />
                      Trending Combinations
                    </CardTitle>
                    <CardDescription>Popular style combinations</CardDescription>
                  </CardHeader>
                  <CardContent className="space-y-3">
                    {trendData.top_combos.slice(0, 10).map((combo, index) => (
                      <div key={index} className="flex items-center p-3 bg-gradient-to-r from-purple-100 to-pink-100 rounded-lg">
                        <span className="font-medium text-gray-700">{combo.combo}</span>
                      </div>
                    ))}
                  </CardContent>
                </Card>

                {/* Trend Entries */}
                <Card className="lg:col-span-2 bg-white/80 backdrop-blur-sm border-0 shadow-lg">
                  <CardHeader>
                    <CardTitle className="flex items-center gap-2 text-blue-700">
                      <Eye className="w-5 h-5" />
                      Trend Analysis
                    </CardTitle>
                    <CardDescription>Current trending elements</CardDescription>
                  </CardHeader>
                  <CardContent>
                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                      {trendData.trend_entries.map((trend, index) => (
                        <div key={index} className="p-4 bg-gradient-to-br from-blue-50 to-purple-50 rounded-lg border border-blue-200">
                          <div className="flex items-center justify-between mb-2">
                            <Badge variant="outline" className="capitalize">{trend.type}</Badge>
                          </div>
                          <h3 className="font-semibold text-gray-800 capitalize">{trend.canonical}</h3>
                        </div>
                      ))}
                    </div>
                  </CardContent>
                </Card>

                {/* Curated Trends (styled like other cards; shows title + regions) */}
                {Array.isArray(trendData?.curated_trends) && (
                  <Card className="lg:col-span-2 bg-white/80 backdrop-blur-sm border-0 shadow-lg">
                    <CardHeader>
                      <CardTitle className="flex items-center gap-2 text-purple-700">
                        <TrendingUp className="w-5 h-5" />
                        Curated Trends
                      </CardTitle>
                      <CardDescription>Global & regional curated fashion insights</CardDescription>
                    </CardHeader>

                    <CardContent className="space-y-4">
                      <div className="grid gap-4">
                        {trendData.curated_trends
                          .filter((t: any) =>
                            Boolean(
                              t &&
                              (t.title ||
                                (Array.isArray(t.colors) && t.colors.length) ||
                                (Array.isArray(t.fabrics) && t.fabrics.length) ||
                                (Array.isArray(t.patterns) && t.patterns.length) ||
                                t.regions)
                            )
                          )
                          .map((trend: any, idx: number) => (
                            <div
                              key={idx}
                              className="p-4 bg-gradient-to-r from-purple-50 to-pink-50 rounded-lg border border-purple-100"
                            >
                              <div className="mb-2">
                                <h4 className="font-semibold text-gray-800">
                                  {trend.title || "Curated"}
                                </h4>
                              </div>

                              <div className="space-y-1 text-sm text-gray-700">
                                {trend.colors && Array.isArray(trend.colors) && trend.colors.length > 0 && (
                                  <p>
                                    <strong>Colors:</strong> {trend.colors.join(", ")}
                                  </p>
                                )}

                                {trend.fabrics && Array.isArray(trend.fabrics) && trend.fabrics.length > 0 && (
                                  <p>
                                    <strong>Fabrics:</strong> {trend.fabrics.join(", ")}
                                  </p>
                                )}

                                {trend.patterns && Array.isArray(trend.patterns) && trend.patterns.length > 0 && (
                                  <p>
                                    <strong>Patterns:</strong> {trend.patterns.join(", ")}
                                  </p>
                                )}

                                {/* Regions object (optional) */}
                                {trend.regions && typeof trend.regions === "object" && (
                                  <div className="mt-2">
                                    <strong>Regions:</strong>
                                    <div className="mt-1 space-y-1 ml-2 text-sm">
                                      {Object.entries(trend.regions).map(([regionName, vals]: any, i: number) => {
                                        const list = Array.isArray(vals) ? vals.join(", ") : String(vals);
                                        return (
                                          <div key={i}>
                                            <span className="font-medium">{regionName}:</span>{" "}
                                            <span className="text-gray-700">{list}</span>
                                          </div>
                                        );
                                      })}
                                    </div>
                                  </div>
                                )}

                                {trend.notes && <p><strong>Notes:</strong> {trend.notes}</p>}
                              </div>
                            </div>
                          ))}
                      </div>
                    </CardContent>
                  </Card>
                )}


              </div>
            ) : (
              <div className="text-center py-8">
                <p className="text-gray-600">No trend data available</p>
              </div>
            )}
          </TabsContent>

          {/* Agent 2 - Product Design Generator */}
          <TabsContent value="design" className="space-y-6">

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              {/* Design Form */}
              <Card className="bg-white/80 backdrop-blur-sm border-0 shadow-lg">
                <CardHeader>
                  <CardTitle className="flex items-center gap-2 text-purple-700">
                    <Palette className="w-5 h-5" />
                    Design Attributes
                  </CardTitle>
                  <CardDescription>Select design parameters</CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <Label>Colors</Label>
                      <Select onValueChange={(value) => setDesignForm({ ...designForm, colors: [...designForm.colors, value] })}>
                        <SelectTrigger>
                          <SelectValue placeholder="Select colors" />
                        </SelectTrigger>
                        <SelectContent>
                          {trendData?.top_by_category?.colors?.map(color => (
                            <SelectItem key={color} value={color}>{color}</SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                    <div>
                      <Label>Fabrics</Label>
                      <Select onValueChange={(value) => setDesignForm({ ...designForm, fabrics: [...designForm.fabrics, value] })}>
                        <SelectTrigger>
                          <SelectValue placeholder="Select fabric" />
                        </SelectTrigger>
                        <SelectContent>
                          {trendData?.top_by_category?.fabrics?.map(fabric => (
                            <SelectItem key={fabric} value={fabric}>{fabric}</SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                    <div>
                      <Label>Prints</Label>
                      <Select onValueChange={(value) => setDesignForm({ ...designForm, prints: [...designForm.prints, value] })}>
                        <SelectTrigger>
                          <SelectValue placeholder="Select print" />
                        </SelectTrigger>
                        <SelectContent>
                          {trendData?.top_by_category?.prints?.map(print => (
                            <SelectItem key={print} value={print}>{print}</SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                    <div>
                      <Label>Garment Type</Label>
                      <Select onValueChange={(value) => setDesignForm({ ...designForm, garmentType: value })}>
                        <SelectTrigger>
                          <SelectValue placeholder="Select garment" />
                        </SelectTrigger>
                        <SelectContent>
                          {trendData?.top_by_category?.garment_types?.map(type => (
                            <SelectItem key={type} value={type}>{type}</SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                    <div>
                      <Label>Silhouette</Label>
                      <Select onValueChange={(value) => setDesignForm({ ...designForm, silhouette: value })}>
                        <SelectTrigger>
                          <SelectValue placeholder="Select silhouette" />
                        </SelectTrigger>
                        <SelectContent>
                          {trendData?.top_by_category?.silhouettes?.map(silhouette => (
                            <SelectItem key={silhouette} value={silhouette}>{silhouette}</SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                    <div>
                      <Label>Sleeves</Label>
                      <Select onValueChange={(value) => setDesignForm({ ...designForm, sleeves: value })}>
                        <SelectTrigger>
                          <SelectValue placeholder="Select sleeves" />
                        </SelectTrigger>
                        <SelectContent>
                          {trendData?.top_by_category?.sleeves?.map(sleeve => (
                            <SelectItem key={sleeve} value={sleeve}>{sleeve}</SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                  </div>

                  <div>
                    <Label>Neckline</Label>
                    <Select onValueChange={(value) => setDesignForm({ ...designForm, neckline: value })}>
                      <SelectTrigger>
                        <SelectValue placeholder="Select neckline" />
                      </SelectTrigger>
                      <SelectContent>
                        {trendData?.top_by_category?.necklines?.map(neckline => (
                          <SelectItem key={neckline} value={neckline}>{neckline}</SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>

                  <div className="md:col-span-2">
                    <Label>Description </Label>
                    <Textarea
                      placeholder="Describe look, mood, special requests (e.g., navy V-neck, lightweight cotton, tonal embroidery). This will be merged into the image prompt."
                      className="mt-2"
                      rows={3}
                      value={designForm.description}
                      onChange={(e) => setDesignForm({ ...designForm, description: e.target.value })}
                    />
                  </div>



                  <Button
                    onClick={() => {
                      // allow generation when either garmentType is selected OR description text provided
                      const hasGarment = !!(designForm && (designForm.garmentType && designForm.garmentType.length));
                      const hasDescription = !!(designForm && designForm.description && designForm.description.trim().length);
                      if (!hasGarment && !hasDescription) {
                        alert("Please select a garment type or enter a description before generating.");
                        return;
                      }

                      // optional: set current design immediately (optimistic UI)
                      // setCurrentDesign(designForm);

                      handleGenerateDesign();
                    }}
                    disabled={isGenerating}
                  >
                    {isGenerating ? "Generating…" : "Generate"}
                  </Button>



                  {isGenerating && (
                    <div className="space-y-2">
                      <Progress value={generationProgress} className="w-full" />
                      <p className="text-sm text-gray-600 text-center">Generating design...</p>
                    </div>
                  )}
                </CardContent>
              </Card>

              {/* Design Output */}
              {/* Design Output */}
              <Card className="bg-white/80 backdrop-blur-sm border-0 shadow-lg">
                <CardHeader>
                  <CardTitle className="flex items-center gap-2 text-pink-700">
                    <Shirt className="w-5 h-5" />
                    Generated Flatlay
                  </CardTitle>
                  <CardDescription>Visual output from description</CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                  {flatlayUrl ? (
                    <div className="aspect-square bg-gray-50 rounded-lg flex items-center justify-center">
                      <img src={flatlayUrl} alt="Flatlay" className="w-full h-full object-contain rounded-lg" />
                    </div>
                  ) : (
                    <div className="text-center py-8 text-gray-500">
                      <Shirt className="w-12 h-12 mx-auto mb-2 text-gray-300" />
                      <p>Generate a design to see the flatlay</p>
                    </div>
                  )}

                  {/* Edit Design (replace with this) */}
                  <div>
                    <Label>Edit Design (plain text instruction)</Label>
                    <Textarea
                      value={editText}
                      onChange={(e) => setEditText(e.target.value)}
                      placeholder="e.g., change to olive linen, square neck, puff sleeves"
                      className="mt-2"
                    />

                    <div className="mt-2 flex gap-2">
                      <Button
                        className="flex-1"
                        onClick={async () => {
                          await handleApplyChange();
                        }}
                        disabled={!currentDesign || applyingChange}
                      >
                        {applyingChange ? "Applying…" : "Apply Changes"}
                      </Button>

                      <Button
                        variant="ghost"
                        onClick={() => {
                          // quick reset to original design JSON if needed
                          setEditText(currentDesign?.design_text || "");
                        }}
                      >
                        Reset
                      </Button>
                    </div>
                  </div>

                </CardContent>
              </Card>
            </div>
          </TabsContent>

          {/* Agent 3 - Virtual Showcase */}
          <TabsContent value="showcase" className="space-y-6">
            {/* Model Customization */}
            <Card className="bg-white/80 backdrop-blur-sm border-0 shadow-lg">
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-blue-700">
                  <Eye className="w-5 h-5" />
                  Model Customization
                </CardTitle>
                <CardDescription>Customize model for showcase</CardDescription>
              </CardHeader>
              <CardContent>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                  <div>
                    <Label>Gender</Label>
                    <Select value={modelConfig.gender} onValueChange={(value) => setModelConfig({ ...modelConfig, gender: value })}>
                      <SelectTrigger>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="female">Female</SelectItem>
                        <SelectItem value="male">Male</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                  <div>
                    <Label>Body Type</Label>
                    <Select value={modelConfig.bodyType} onValueChange={(value) => setModelConfig({ ...modelConfig, bodyType: value })}>
                      <SelectTrigger>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="slim">Slim</SelectItem>
                        <SelectItem value="athletic">Athletic</SelectItem>
                        <SelectItem value="curvy">Curvy</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                  <div>
                    <Label>Skin Tone</Label>
                    <Select value={modelConfig.skinTone} onValueChange={(value) => setModelConfig({ ...modelConfig, skinTone: value })}>
                      <SelectTrigger>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="light">Light</SelectItem>
                        <SelectItem value="medium">Medium</SelectItem>
                        <SelectItem value="dark">Dark</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                  <div>
                    <Label>Pose</Label>
                    <Select value={modelConfig.pose} onValueChange={(value) => setModelConfig({ ...modelConfig, pose: value })}>
                      <SelectTrigger>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="walk">Walk</SelectItem>
                        <SelectItem value="turn">Turn</SelectItem>
                        <SelectItem value="pose">Pose</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                </div>
              </CardContent>
            </Card>

            {/* Generation Options */}
            <div className="grid grid-cols-1 md:grid-cols-4 gap-6">


              <Card className="bg-white/80 backdrop-blur-sm border-0 shadow-lg md:col-span-2">
                <CardHeader>
                  <CardTitle className="flex items-center gap-2 text-pink-700">
                    <Shirt className="w-5 h-5" />
                    Virtual Showcase
                  </CardTitle>
                  <CardDescription>Model wearing apparel</CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="aspect-square bg-gradient-to-br from-pink-100 to-blue-100 rounded-lg flex items-center justify-center">
                    {showcaseUrl ? (
                      <img src={showcaseUrl} alt="Showcase" className="w-full h-full object-contain rounded-lg" />
                    ) : (
                      <div className="text-center">
                        <Shirt className="w-12 h-12 mx-auto text-pink-400 mb-2" />
                        <p className="text-sm text-gray-600">Model showcase</p>
                      </div>
                    )}
                  </div>
                  <Button onClick={() => handleVirtualShowcase(modelConfig)} >Virtual Showcase</Button>

                </CardContent>
              </Card>

              <Card className="bg-white/80 backdrop-blur-sm border-0 shadow-lg md:col-span-2">
                <CardHeader>
                  <CardTitle className="flex items-center gap-2 text-blue-700">
                    <Play className="w-5 h-5" />
                    Runway Video
                  </CardTitle>
                  <CardDescription>6s fashion video</CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="aspect-square bg-gradient-to-br from-green-100 to-yellow-100 rounded-lg flex items-center justify-center">
                    {runwayUrl ? (
                      <video
                        src={runwayUrl}
                        controls
                        playsInline
                        // optional: autoplay muted loop
                        // autoPlay muted loop
                        className="w-full h-full object-contain rounded-lg"
                      >
                        Your browser does not support the video tag.
                      </video>
                    ) : (
                      <div className="text-center">
                        <video className="w-12 h-12 mx-auto text-green-400 mb-2" />
                        <p className="text-sm text-gray-600">Runway video</p>
                      </div>
                    )}
                  </div>

                  <Button onClick={() => handleRunway(modelConfig)} >Generate Runway</Button>

                </CardContent>
              </Card>
            </div>

            {/* Export Options */}
            <Card className="bg-white/80 backdrop-blur-sm border-0 shadow-lg">
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-green-700">
                  <Download className="w-5 h-5" />
                  Export Options
                </CardTitle>
                <CardDescription>Download generated content</CardDescription>
              </CardHeader>
              <CardContent>
                <div className="flex flex-wrap gap-4">
                  <Button variant="outline" className="flex items-center gap-2">
                    <Download className="w-4 h-4" />
                    Download Lookbook
                  </Button>
                  <Button variant="outline" className="flex items-center gap-2">
                    <Play className="w-4 h-4" />
                    Export Runway Video
                  </Button>
                  <Button variant="outline" className="flex items-center gap-2">
                    <Eye className="w-4 h-4" />
                    Export All Assets
                  </Button>
                </div>
              </CardContent>
            </Card>

            {isGenerating && (
              <Alert>
                <AlertDescription>
                  Generating your fashion content... This may take a few moments.
                </AlertDescription>
              </Alert>
            )}
          </TabsContent>
        </Tabs >
      </div >
    </div >
  )
}