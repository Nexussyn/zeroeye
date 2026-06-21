use flate2::{read::GzDecoder, write::GzEncoder, Compression};
use serde::{Deserialize, Serialize};
use std::io::{Read, Write};
use zstd::{stream::{decode_all, encode_all}};

#[derive(Debug, Clone, Copy, PartialEq, Default)]
pub enum CompressionFormat {
    #[default]
    None,
    Gzip,
    Zstd,
}

#[derive(Debug, Clone)]
pub struct CompressionConfig {
    pub format: CompressionFormat,
    pub level: i32,
}

impl Default for CompressionConfig {
    fn default() -> Self {
        Self { format: CompressionFormat::None, level: 3 }
    }
}

#[derive(Debug, Clone)]
pub struct Serializer {
    config: CompressionConfig,
}

impl Serializer {
    pub fn new(config: CompressionConfig) -> Self {
        Self { config }
    }

    pub fn serialize<T: Serialize>(&self, value: &T) -> Result<Vec<u8>, Box<dyn std::error::Error>> {
        let json_bytes = serde_json::to_vec(value)?;
        self.compress(&json_bytes)
    }

    pub fn deserialize<T: for<'a> Deserialize<'a>>(&self, data: &[u8]) -> Result<T, Box<dyn std::error::Error>> {
        let decompressed = self.decompress(data)?;
        Ok(serde_json::from_slice(&decompressed)?)
    }

    fn compress(&self, data: &[u8]) -> Result<Vec<u8>, Box<dyn std::error::Error>> {
        match self.config.format {
            CompressionFormat::None => Ok(data.to_vec()),
            CompressionFormat::Gzip => {
                let level = Compression::new(self.config.level as u32);
                let mut encoder = GzEncoder::new(Vec::new(), level);
                encoder.write_all(data)?;
                Ok(encoder.finish()?)
            }
            CompressionFormat::Zstd => Ok(encode_all(data, self.config.level)?),
        }
    }

    fn decompress(&self, data: &[u8]) -> Result<Vec<u8>, Box<dyn std::error::Error>> {
        match self.config.format {
            CompressionFormat::None => Ok(data.to_vec()),
            CompressionFormat::Gzip => {
                let mut decoder = GzDecoder::new(data);
                let mut out = Vec::new();
                decoder.read_to_end(&mut out)?;
                Ok(out)
            }
            CompressionFormat::Zstd => Ok(decode_all(data)?),
        }
    }
}
