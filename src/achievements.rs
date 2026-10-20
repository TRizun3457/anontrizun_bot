/// A single achievement definition. The order matches the original mapping.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Achievement {
    pub id: &'static str,
    pub title: &'static str,
    pub description: &'static str,
    pub icon: &'static str,
}

pub const ACHIEVEMENTS: &[Achievement] = &[
    Achievement {
        id: "bro_42",
        title: "42 братуха",
        description: "Написать '42' в анонимном сообщении",
        icon: "🤖",
    },
    Achievement {
        id: "air_1",
        title: "Воздухан обнаружен!",
        description: "Купить воздух 1 раз",
        icon: "💨",
    },
    Achievement {
        id: "air_10",
        title: "Становится ветренно",
        description: "Купить воздух 10 раз",
        icon: "🌬️",
    },
    Achievement {
        id: "air_100",
        title: "Ураган",
        description: "Купить воздух 100 раз",
        icon: "🌪️",
    },
    Achievement {
        id: "vip_access",
        title: "Добро пожаловать в VIP зону",
        description: "Приобрести VIP-оформление",
        icon: "💎",
    },
    Achievement {
        id: "degrade_67",
        title: "Деградируем",
        description: "Отправить '67' анонимно",
        icon: "🤪",
    },
    Achievement {
        id: "anon_first",
        title: "Аноним",
        description: "Отправить первое анонимное сообщение",
        icon: "🕵️",
    },
    Achievement {
        id: "who_are_you",
        title: "Кто ты?",
        description: "Отправить 100 анонимных сообщений",
        icon: "❓",
    },
    Achievement {
        id: "secret_fan",
        title: "Тайный фанат",
        description: "Отправить 200 анонимных сообщений",
        icon: "❤️",
    },
    Achievement {
        id: "vip_person",
        title: "Важная персона",
        description: "Отправить 10 приоритетных сообщений",
        icon: "⭐",
    },
    Achievement {
        id: "first_donate",
        title: "Оооо кто-то мне задонатил!",
        description: "Сделать первую любую покупку в боте",
        icon: "🤑",
    },
    Achievement {
        id: "not_interested",
        title: "Сорри не интересно",
        description: "Не получить ответа 20 раз",
        icon: "💔",
    },
    Achievement {
        id: "answer_streak_15",
        title: "Целая серия",
        description: "Получить 15 ответов подряд на разных сообщениях",
        icon: "🔥",
    },
    Achievement {
        id: "star_fall",
        title: "Звезда упала",
        description: "Потратить более 100 звезд в боте",
        icon: "🌠",
    },
    Achievement {
        id: "impossible",
        title: "Невозможное возможно",
        description: "Выдается одним из Contributors проекта",
        icon: "🏆",
    },
];

pub fn get(id: &str) -> Option<&'static Achievement> {
    ACHIEVEMENTS.iter().find(|achievement| achievement.id == id)
}

pub const fn total_count() -> usize {
    ACHIEVEMENTS.len()
}

/// The subset of user statistics used to evaluate earned achievements.
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub struct AchievementStats {
    pub air_purchased: i64,
    pub sent_count: i64,
    pub received_count: i64,
    pub is_vip: bool,
    pub priority_sent_count: i64,
    pub total_spent_stars: i64,
    pub answer_streak: i64,
}

/// Returns every achievement whose condition currently holds, in the same
/// order as [`ACHIEVEMENTS`].
pub fn satisfied(stats: &AchievementStats) -> Vec<&'static str> {
    let mut achieved = Vec::new();

    let mut check = |id: &'static str, condition: bool| {
        if condition {
            achieved.push(id);
        }
    };

    check("air_1", stats.air_purchased >= 1);
    check("air_10", stats.air_purchased >= 10);
    check("air_100", stats.air_purchased >= 100);
    check("vip_access", stats.is_vip);
    check("anon_first", stats.sent_count >= 1);
    check("who_are_you", stats.sent_count >= 100);
    check("secret_fan", stats.sent_count >= 200);
    check("vip_person", stats.priority_sent_count >= 10);
    check(
        "not_interested",
        stats.sent_count - stats.received_count >= 20,
    );
    check("answer_streak_15", stats.answer_streak >= 15);
    check("star_fall", stats.total_spent_stars > 100);

    achieved
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn definitions_are_complete_and_unique() {
        assert_eq!(total_count(), 15);

        let mut ids: Vec<_> = ACHIEVEMENTS.iter().map(|a| a.id).collect();
        ids.sort_unstable();
        ids.dedup();
        assert_eq!(ids.len(), ACHIEVEMENTS.len());

        for achievement in ACHIEVEMENTS {
            assert!(!achievement.title.is_empty());
            assert!(!achievement.description.is_empty());
            assert!(!achievement.icon.is_empty());
        }
    }

    #[test]
    fn default_stats_satisfy_nothing() {
        assert!(satisfied(&AchievementStats::default()).is_empty());
    }

    #[test]
    fn air_thresholds() {
        let mut stats = AchievementStats {
            air_purchased: 1,
            ..AchievementStats::default()
        };
        assert!(satisfied(&stats).contains(&"air_1"));

        stats.air_purchased = 9;
        assert!(!satisfied(&stats).contains(&"air_10"));
        stats.air_purchased = 10;
        assert!(satisfied(&stats).contains(&"air_10"));

        stats.air_purchased = 99;
        assert!(!satisfied(&stats).contains(&"air_100"));
        stats.air_purchased = 100;
        assert!(satisfied(&stats).contains(&"air_100"));
    }

    #[test]
    fn sent_thresholds() {
        let mut stats = AchievementStats {
            sent_count: 1,
            ..AchievementStats::default()
        };
        assert!(satisfied(&stats).contains(&"anon_first"));

        stats.sent_count = 99;
        assert!(!satisfied(&stats).contains(&"who_are_you"));
        stats.sent_count = 100;
        assert!(satisfied(&stats).contains(&"who_are_you"));

        stats.sent_count = 199;
        assert!(!satisfied(&stats).contains(&"secret_fan"));
        stats.sent_count = 200;
        assert!(satisfied(&stats).contains(&"secret_fan"));
    }

    #[test]
    fn not_interested_uses_difference() {
        let stats = AchievementStats {
            sent_count: 25,
            received_count: 5,
            ..AchievementStats::default()
        };
        assert!(satisfied(&stats).contains(&"not_interested"));

        let stats = AchievementStats {
            sent_count: 24,
            received_count: 5,
            ..AchievementStats::default()
        };
        assert!(!satisfied(&stats).contains(&"not_interested"));
    }

    #[test]
    fn star_fall_requires_more_than_hundred() {
        let stats = AchievementStats {
            total_spent_stars: 100,
            ..AchievementStats::default()
        };
        assert!(!satisfied(&stats).contains(&"star_fall"));

        let stats = AchievementStats {
            total_spent_stars: 101,
            ..AchievementStats::default()
        };
        assert!(satisfied(&stats).contains(&"star_fall"));
    }

    #[test]
    fn answer_streak_threshold() {
        let stats = AchievementStats {
            answer_streak: 14,
            ..AchievementStats::default()
        };
        assert!(!satisfied(&stats).contains(&"answer_streak_15"));

        let stats = AchievementStats {
            answer_streak: 15,
            ..AchievementStats::default()
        };
        assert!(satisfied(&stats).contains(&"answer_streak_15"));
    }
}
