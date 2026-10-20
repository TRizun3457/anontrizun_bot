//! Inline query sharing.

use std::sync::Arc;

use teloxide::types::{
    InlineQuery, InlineQueryResult, InlineQueryResultArticle, InputMessageContent,
    InputMessageContentText, ParseMode,
};

use crate::app::AppState;
use crate::error::{HandlerResult, guarded_inline};
use crate::handlers::user::helpers;
use crate::keyboards;
use crate::texts;

pub async fn inline_query_handler(
    state: Arc<AppState>,
    inline_query: InlineQuery,
) -> HandlerResult {
    guarded_inline(&inline_query, async {
        let user_id = inline_query.from.id.0 as i64;
        let user_stats = state.db.register_user(user_id, None).await?;
        let mut results: Vec<InlineQueryResult> = Vec::new();

        if user_id == state.config.admin_id {
            let keyboard = keyboards::inline_admin_keyboard(&state.bot_username)?;
            results.push(InlineQueryResult::Article(
                InlineQueryResultArticle::new(
                    "admin_share",
                    texts::INLINE_ADMIN_TITLE,
                    InputMessageContent::Text(
                        InputMessageContentText::new(texts::INLINE_ADMIN_SHARE_TEXT)
                            .parse_mode(ParseMode::Html),
                    ),
                )
                .description(texts::INLINE_ADMIN_DESCRIPTION)
                .reply_markup(keyboard),
            ));
        }

        let achievements_count = state.db.get_user_achievements_count(user_id).await?;
        let cat = helpers::cat_for(&user_stats);
        let stats_text = texts::share_preview_text(
            &user_stats,
            achievements_count,
            crate::achievements::total_count(),
            &cat,
        );

        let keyboard = keyboards::inline_user_keyboard(&state.bot_username)?;
        results.push(InlineQueryResult::Article(
            InlineQueryResultArticle::new(
                "user_status_share",
                texts::inline_share_title(&user_stats),
                InputMessageContent::Text(
                    InputMessageContentText::new(stats_text).parse_mode(ParseMode::Html),
                ),
            )
            .description(texts::INLINE_STATS_DESCRIPTION)
            .reply_markup(keyboard),
        ));

        state
            .api
            .answer_inline(inline_query.id.clone(), results)
            .await?;
        Ok(())
    })
    .await
}
