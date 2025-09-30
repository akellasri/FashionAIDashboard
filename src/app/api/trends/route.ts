import { NextRequest, NextResponse } from 'next/server'
import { readFile } from 'fs/promises'
import path from 'path'

export async function GET(request: NextRequest) {
  try {
    // Read the actual trends_index.json file
    const filePath = path.join(process.cwd(), 'trends_index.json')
    const fileContent = await readFile(filePath, 'utf-8')
    const trendData = JSON.parse(fileContent)
    
    return NextResponse.json(trendData)
  } catch (error) {
    console.error('Error loading trend data:', error)
    
    // Fallback to sample data if file not found
    const fallbackData = {
      generated_at: "2025-09-24T12:24:33.444177+00:00",
      records_count: 1410,
      top_by_category: {
        colors: ["brown", "white", "grey", "cream", "black", "red", "olive", "beige", "blue", "pink"],
        fabrics: ["cotton", "silk", "linen", "satin", "chiffon", "lace", "denim", "rayon", "chikankari", "crepe"],
        prints: ["embroidery", "solids / minimalist", "florals", "bandhani", "ikat", "block print", "geometric", "paisley", "polka dot", "floral"],
        silhouettes: ["Draped/Flowing", "A-line", "Tailored", "Fit-and-flare", "sheath", "Bodycon/Fitted", "anarkali", "Oversized/Baggy", "slip dress", "asymmetric"],
        sleeves: ["Full sleeves", "Sleeveless/Tank", "short sleeve", "3/4th sleeves", "kimono sleeve", "bell sleeve"],
        necklines: ["Crew neck", "V-neck", "Collared", "Halter", "Square neck", "Sweetheart neck", "Off-shoulder", "Asymmetrical/One-shoulder", "Cowl neck"],
        garment_types: ["dress", "kurta", "kurta-set", "coord set", "top", "shirt", "lehenga", "sari", "jacket", "skirt"],
        lengths: ["Full-length", "Midi", "Mini", "Ankle-length", "Maxi", "Cropped", "Knee-length"]
      },
      top_combos: [
        { combo: "color:brown | color:white", weight: 329 },
        { combo: "color:grey | color:white", weight: 260 },
        { combo: "color:white | garment:dress", weight: 240 },
        { combo: "color:white | print:solids / minimalist", weight: 239 },
        { combo: "color:red | color:white", weight: 199 }
      ],
      trend_entries: [
        { trend_id: "fabric:cotton", type: "fabric", canonical: "cotton", count: 282, score: 1.18 },
        { trend_id: "print:embroidery", type: "print", canonical: "embroidery", count: 285, score: 1.12 },
        { trend_id: "print:solids / minimalist", type: "print", canonical: "solids / minimalist", count: 397, score: 1.11 },
        { trend_id: "color:brown", type: "color", canonical: "brown", count: 580, score: 1.09 },
        { trend_id: "color:white", type: "color", canonical: "white", count: 804, score: 1.05 }
      ]
    }
    
    return NextResponse.json(fallbackData)
  }
}