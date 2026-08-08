/* ==========================================
   GAJANAN UTSAV SAMITI 2026
   Main JavaScript
========================================== */

document.addEventListener("DOMContentLoaded", function () {

    /* ===========================
       Mobile Menu
    =========================== */

    const menuBtn = document.getElementById("menuBtn");
    const navMenu = document.getElementById("navMenu");

    if (menuBtn && navMenu) {

        menuBtn.addEventListener("click", function () {

            navMenu.classList.toggle("active");

            menuBtn.innerHTML = navMenu.classList.contains("active")
                ? '<i class="fa-solid fa-xmark"></i>'
                : '<i class="fa-solid fa-bars"></i>';

        });

    }

    /* ===========================
       Sticky Navbar
    =========================== */

    const navbar = document.querySelector(".navbar");

    window.addEventListener("scroll", function () {

        if (!navbar) return;

        navbar.style.boxShadow =
            window.scrollY > 20
                ? "0 10px 25px rgba(0,0,0,.08)"
                : "none";

    });

    /* ===========================
       Back To Top
    =========================== */

    const topBtn = document.getElementById("topBtn");

    window.addEventListener("scroll", function () {

        if (!topBtn) return;

        topBtn.style.display =
            window.scrollY > 500 ? "block" : "none";

    });

    if (topBtn) {

        topBtn.addEventListener("click", function () {

            window.scrollTo({
                top: 0,
                behavior: "smooth"
            });

        });

    }



    /* ===========================
       Fade Animation
    =========================== */

    if ("IntersectionObserver" in window) {

        const observer = new IntersectionObserver(function (entries) {

            entries.forEach(function (entry) {

                if (entry.isIntersecting) {

                    entry.target.classList.add("show");

                }

            });

        }, {
            threshold: 0.15
        });

        document.querySelectorAll(".fade-up").forEach(function (el) {

            observer.observe(el);

        });

    }

    /* ===========================
       Page Loaded
    =========================== */

    document.body.classList.add("loaded");

    /* ===========================
       Countdown
    =========================== */

    const days = document.getElementById("days");
    const hours = document.getElementById("hours");
    const minutes = document.getElementById("minutes");
    const seconds = document.getElementById("seconds");

    if (days && hours && minutes && seconds) {

        const target = new Date("2026-09-14T08:00:00").getTime();

        function updateCountdown() {

            const now = new Date().getTime();
            const distance = target - now;

            if (distance <= 0) {

                days.textContent = "00";
                hours.textContent = "00";
                minutes.textContent = "00";
                seconds.textContent = "00";

                return;
            }

            days.textContent = Math.floor(distance / (1000 * 60 * 60 * 24));

            hours.textContent = Math.floor(
                (distance % (1000 * 60 * 60 * 24)) /
                (1000 * 60 * 60)
            );

            minutes.textContent = Math.floor(
                (distance % (1000 * 60 * 60)) /
                (1000 * 60)
            );

            seconds.textContent = Math.floor(
                (distance % (1000 * 60)) /
                1000
            );

        }

        updateCountdown();

        setInterval(updateCountdown, 1000);

    }

    /* ===========================
       Gallery Lightbox
    =========================== */

    const images = document.querySelectorAll(".gallery-image");

    const lightbox = document.getElementById("lightbox");
    const lightboxImg = document.getElementById("lightboxImg");
    const closeBtn = document.getElementById("closeBtn");
    const nextBtn = document.getElementById("nextBtn");
    const prevBtn = document.getElementById("prevBtn");

    if (
        images.length &&
        lightbox &&
        lightboxImg &&
        closeBtn &&
        nextBtn &&
        prevBtn
    ) {

        let current = 0;

        function showImage() {

            lightbox.style.display = "flex";
            lightboxImg.src = images[current].src;

        }

        images.forEach(function (img, index) {

            img.addEventListener("click", function () {

                current = index;
                showImage();

            });

        });

        closeBtn.addEventListener("click", function () {

            lightbox.style.display = "none";

        });

        nextBtn.addEventListener("click", function () {

            current = (current + 1) % images.length;
            showImage();

        });

        prevBtn.addEventListener("click", function () {

            current = (current - 1 + images.length) % images.length;
            showImage();

        });

        lightbox.addEventListener("click", function (e) {

            if (e.target === lightbox) {

                lightbox.style.display = "none";

            }

        });

        document.addEventListener("keydown", function (e) {

            if (lightbox.style.display !== "flex") return;

            if (e.key === "Escape") {

                lightbox.style.display = "none";

            }

            if (e.key === "ArrowRight") {

                current = (current + 1) % images.length;
                showImage();

            }

            if (e.key === "ArrowLeft") {

                current = (current - 1 + images.length) % images.length;
                showImage();

            }

        });

    }

});
/* ==============================
   Scroll Reveal
============================== */

const revealElements = document.querySelectorAll(
".reveal,.reveal-left,.reveal-right,.reveal-scale"
);

function revealOnScroll(){

    revealElements.forEach(el=>{

        const windowHeight=window.innerHeight;

        const elementTop=el.getBoundingClientRect().top;

        const visible=120;

        if(elementTop<windowHeight-visible){

            el.classList.add("active");

        }

    });

}

window.addEventListener("scroll",revealOnScroll);

window.addEventListener("load",revealOnScroll);
/* ==============================
   Animated Counter
============================== */

const counters = document.querySelectorAll(".counter");

let counterStarted = false;

function startCounters() {

    if (counterStarted) return;

    const statsSection = document.querySelector(".stats");

    if (!statsSection) return;

    const sectionTop = statsSection.getBoundingClientRect().top;

    if (sectionTop < window.innerHeight - 100) {

        counterStarted = true;

        counters.forEach(counter => {

            const target = +counter.dataset.target;

            let count = 0;

            const speed = Math.max(20, Math.floor(1500 / target));

            const update = () => {

                if (count < target) {

                    count++;

                    if (target >= 100) {

                        counter.innerText = count + "+";

                    } else {

                        counter.innerText = count;

                    }

                    setTimeout(update, speed);

                } else {

                    if (target >= 100) {

                        counter.innerText = target + "+";

                    } else {

                        counter.innerText = target;

                    }

                }

            };

            update();

        });

    }

}

window.addEventListener("scroll", startCounters);

window.addEventListener("load", startCounters);
/* ===============================
   PRELOADER
=============================== */

window.addEventListener("load",()=>{

    const preloader=document.getElementById("preloader");

    if(preloader){

        setTimeout(()=>{

            preloader.classList.add("hide");

        },1200);

    }

});

/* ===============================
   WINNER SEARCH & FILTER
=============================== */

document.addEventListener("DOMContentLoaded", () => {

    const searchInput = document.getElementById("winnerSearch");
    const yearFilter = document.getElementById("yearFilter");
    const gameFilter = document.getElementById("gameFilter");

    if (!searchInput || !yearFilter || !gameFilter) return;

    const cards = document.querySelectorAll(".winner-card");
    const sections = document.querySelectorAll(".winner-year");

    function filterWinners() {

        const search = searchInput.value.toLowerCase().trim();
        const year = yearFilter.value;
        const game = gameFilter.value;

        cards.forEach(card => {

            const cardYear = card.dataset.year;
            const cardGame = card.dataset.game;
            const searchText = card.dataset.search;

            let visible = true;

            if (year !== "all" && cardYear !== year)
                visible = false;

            if (game !== "all" && cardGame !== game)
                visible = false;

            if (search && !searchText.includes(search))
                visible = false;

            card.style.display = visible ? "" : "none";

        });

        sections.forEach(section => {

            const visibleCards = section.querySelectorAll(".winner-card:not([style*='display: none'])");

            section.style.display = visibleCards.length ? "" : "none";

        });

    }

    searchInput.addEventListener("keyup", filterWinners);
    yearFilter.addEventListener("change", filterWinners);
    gameFilter.addEventListener("change", filterWinners);

});

/* =========================
   HOME GALLERY SLIDER
========================= */

document.addEventListener("DOMContentLoaded", function () {

    const slider = document.querySelector(".gallery-slider");

    if (!slider) {
        return;
    }

    const slides = slider.querySelectorAll(".gallery-slide");
    const dots = slider.querySelectorAll(".gallery-dot");

    const prevBtn = slider.querySelector(".gallery-prev");
    const nextBtn = slider.querySelector(".gallery-next");

    if (slides.length <= 1) {
        return;
    }

    let currentSlide = 0;
    let autoSlide;

    function showSlide(index) {

        if (index >= slides.length) {
            index = 0;
        }

        if (index < 0) {
            index = slides.length - 1;
        }

        slides.forEach(function (slide) {
            slide.classList.remove("active");
        });

        dots.forEach(function (dot) {
            dot.classList.remove("active");
        });

        slides[index].classList.add("active");

        if (dots[index]) {
            dots[index].classList.add("active");
        }

        currentSlide = index;
    }

    function nextSlide() {
        showSlide(currentSlide + 1);
    }

    function prevSlide() {
        showSlide(currentSlide - 1);
    }

    function startAutoSlide() {

        clearInterval(autoSlide);

        autoSlide = setInterval(function () {
            nextSlide();
        }, 4000);

    }

    if (nextBtn) {

        nextBtn.addEventListener("click", function () {
            nextSlide();
            startAutoSlide();
        });

    }

    if (prevBtn) {

        prevBtn.addEventListener("click", function () {
            prevSlide();
            startAutoSlide();
        });

    }

    dots.forEach(function (dot, index) {

        dot.addEventListener("click", function () {
            showSlide(index);
            startAutoSlide();
        });

    });

    showSlide(0);
    startAutoSlide();

});


/* =========================
   ADMIN GALLERY UPLOAD PREVIEW
========================= */

document.addEventListener("DOMContentLoaded", function () {

    const fileInput = document.querySelector('input[name="photos"]');
    const preview = document.getElementById("uploadPreview");

    if (!fileInput || !preview) {
        return;
    }

    fileInput.addEventListener("change", function () {

        preview.innerHTML = "";

        const files = Array.from(fileInput.files);

        files.forEach(function (file) {

            if (!file.type.startsWith("image/")) {
                return;
            }

            const reader = new FileReader();

            reader.onload = function (e) {

                const item = document.createElement("div");
                item.className = "upload-preview-item";

                item.innerHTML = `
                    <img src="${e.target.result}" alt="Preview">
                    <span>${file.name}</span>
                `;

                preview.appendChild(item);
            };

            reader.readAsDataURL(file);
        });

    });

});
