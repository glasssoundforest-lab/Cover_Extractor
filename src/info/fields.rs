use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct ScenarioInfo {
    #[serde(skip_serializing_if = "Option::is_none")]
    pub title: Option<InfoValue<String>>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub system: Option<InfoValue<String>>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub players: Option<InfoValue<PlayerCount>>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub duration: Option<InfoValue<DurationInfo>>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub genre: Option<InfoValue<String>>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub lost: Option<InfoValue<String>>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub format: Option<InfoValue<String>>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub skills: Option<InfoValue<Vec<String>>>,
    /// スペック概要 (推奨人数・時間・技能等)
    #[serde(skip_serializing_if = "Option::is_none")]
    pub overview: Option<InfoValue<String>>,
    /// ストーリーあらすじ
    #[serde(skip_serializing_if = "Option::is_none")]
    pub synopsis: Option<InfoValue<String>>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct InfoValue<T> {
    pub value: T,
    pub source_path: String,
    pub raw_text: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PlayerCount {
    pub min: u32,
    pub max: u32,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DurationInfo {
    pub min_hours: u32,
    pub max_hours: u32,
}