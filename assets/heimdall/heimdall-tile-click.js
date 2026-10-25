/* Heimdall 整卡点击跳转 · Kimi 2026-10-25 */
(function () {
    function bindTileClicks() {
        document.querySelectorAll('section.item-container').forEach(function (sec) {
            var item = sec.querySelector('.item');
            var link = sec.querySelector('.item a.link');
            if (!item || !link || item.dataset.tileClickBound) return;
            item.dataset.tileClickBound = '1';
            item.addEventListener('click', function (e) {
                // 链接、编辑按钮自身按原逻辑处理，避免重复触发
                if (e.target.closest('a')) return;
                link.click(); // 复用原链接行为（含 target 属性）
            });
        });
    }
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', bindTileClicks);
    } else {
        bindTileClicks();
    }
})();
