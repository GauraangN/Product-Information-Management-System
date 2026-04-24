/**
 * PIM Seasonal Integration JavaScript
 * Handles dynamic product loading and filtering on WooCommerce frontend
 */

jQuery(document).ready(function($) {
    let currentSeason = '';
    let customerLocation = '';
    let isLoading = false;
    
    // Initialize seasonal context
    function initSeasonalContext() {
        $.ajax({
            url: pim_ajax.ajax_url,
            type: 'POST',
            data: {
                action: 'get_seasonal_context',
                nonce: pim_ajax.nonce
            },
            success: function(response) {
                if (response.success) {
                    currentSeason = response.data.season;
                    customerLocation = response.data.location;
                    updateSeasonalUI(response.data);
                }
            }
        });
    }
    
    // Update UI with seasonal information
    function updateSeasonalUI(context) {
        // Update seasonal banner
        $('.seasonal-banner').html(`
            <div class="seasonal-content">
                <h3>🌟 ${context.season.charAt(0).toUpperCase() + context.season.slice(1)} Collection</h3>
                <p>Perfect ${context.season} picks for ${context.location || 'your location'}!</p>
            </div>
        `);
        
        // Add seasonal filters to sidebar
        addSeasonalFilters(context.recommendations);
    }
    
    // Add seasonal filter widgets
    function addSeasonalFilters(recommendations) {
        if (!$('.seasonal-filters-widget').length) {
            $('.widget-area').append(`
                <div class="widget seasonal-filters-widget">
                    <h3>Seasonal Filters</h3>
                    <div class="seasonal-filter-content">
                        <div class="current-season">
                            <strong>Current Season:</strong> ${currentSeason}
                        </div>
                        <div class="featured-categories">
                            <h4>Featured Categories:</h4>
                            <ul class="seasonal-categories">
                                ${recommendations.featured_categories ? 
                                    recommendations.featured_categories.map(cat => 
                                        `<li><a href="#" class="seasonal-category-link" data-category="${cat}">${cat}</a></li>`
                                    ).join('') : ''
                                }
                            </ul>
                        </div>
                        <div class="seasonal-attributes">
                            <h4>Perfect Attributes:</h4>
                            <ul class="seasonal-attributes-list">
                                ${recommendations.attributes ? 
                                    recommendations.attributes.map(attr => 
                                        `<li><span class="attribute-tag">${attr}</span></li>`
                                    ).join('') : ''
                                }
                            </ul>
                        </div>
                    </div>
                </div>
            `);
        }
    }
    
    // Load seasonal products dynamically
    function loadSeasonalProducts(category = null, append = false) {
        if (isLoading) return;
        
        isLoading = true;
        $('.loading-spinner').show();
        
        $.ajax({
            url: pim_ajax.ajax_url,
            type: 'POST',
            data: {
                action: 'get_seasonal_products',
                category: category,
                nonce: pim_ajax.nonce
            },
            success: function(response) {
                if (response.success) {
                    displaySeasonalProducts(response.data.products, append);
                    updateProductCount(response.data.products.length);
                } else {
                    console.error('Failed to load seasonal products:', response.data);
                }
            },
            error: function(xhr, status, error) {
                console.error('AJAX error:', error);
                showErrorMessage('Unable to load products. Please try again.');
            },
            complete: function() {
                isLoading = false;
                $('.loading-spinner').hide();
            }
        });
    }
    
    // Display products with seasonal relevance scores
    function displaySeasonalProducts(products, append = false) {
        const container = $('.products');
        const productsHtml = products.map(product => `
            <div class="product seasonal-product" data-product-id="${product.id}">
                <div class="seasonal-badge" style="background: ${getSeasonalColor(product.seasonal_relevance)}">
                    ${Math.round(product.seasonal_relevance * 100)}% Match
                </div>
                <div class="product-image">
                    <img src="${product.image}" alt="${product.name}">
                </div>
                <div class="product-info">
                    <h3 class="product-title">
                        <a href="${product.url}">${product.name}</a>
                    </h3>
                    <div class="price">${product.price}</div>
                    <div class="product-category">${product.category}</div>
                    <div class="seasonal-score" title="Seasonal relevance">
                        <small>Seasonal Match: ${Math.round(product.seasonal_relevance * 100)}%</small>
                    </div>
                </div>
            </div>
        `).join('');
        
        if (append) {
            container.append(productsHtml);
        } else {
            container.html(productsHtml);
        }
        
        // Trigger WooCommerce events for compatibility
        $(document.body).trigger('wc_fragment_refresh');
    }
    
    // Get color based on seasonal relevance score
    function getSeasonalColor(score) {
        if (score >= 0.8) return '#28a745'; // Green
        if (score >= 0.6) return '#ffc107'; // Yellow
        if (score >= 0.4) return '#fd7e14'; // Orange
        return '#dc3545'; // Red
    }
    
    // Update product count
    function updateProductCount(count) {
        $('.product-count').text(`${count} seasonal products found`);
    }
    
    // Show error message
    function showErrorMessage(message) {
        $('.woocommerce-info').html(`<div class="woocommerce-error">${message}</div>`);
    }
    
    // Event handlers
    $(document).on('click', '.seasonal-category-link', function(e) {
        e.preventDefault();
        const category = $(this).data('category');
        
        // Update active state
        $('.seasonal-category-link').removeClass('active');
        $(this).addClass('active');
        
        // Load products for category
        loadSeasonalProducts(category);
        
        // Update URL
        history.pushState(null, null, `?seasonal_category=${category}`);
    });
    
    // Handle browser back/forward
    $(window).on('popstate', function() {
        const urlParams = new URLSearchParams(window.location.search);
        const category = urlParams.get('seasonal_category');
        loadSeasonalProducts(category);
    });
    
    // Infinite scroll for seasonal products
    $(window).on('scroll', function() {
        if ($(window).scrollTop() + $(window).height() > $(document).height() - 100) {
            if (!isLoading && $('.load-more-seasonal').length) {
                loadSeasonalProducts(null, true);
            }
        }
    });
    
    // Add loading spinner
    function addLoadingSpinner() {
        if (!$('.loading-spinner').length) {
            $('.woocommerce-products-header').after(`
                <div class="loading-spinner" style="display: none; text-align: center; padding: 20px;">
                    <div class="spinner" style="border: 4px solid #f3f3f3; border-top: 4px solid #3498db; border-radius: 50%; width: 40px; height: 40px; animation: spin 1s linear infinite; margin: 0 auto;"></div>
                    <p>Loading seasonal products...</p>
                </div>
            `);
        }
    }
    
    // Add CSS animations
    const style = document.createElement('style');
    style.textContent = `
        @keyframes spin {
            0% { transform: rotate(0deg); }
            100% { transform: rotate(360deg); }
        }
        
        .seasonal-product {
            position: relative;
            border: 1px solid #ddd;
            border-radius: 8px;
            overflow: hidden;
            transition: transform 0.3s ease, box-shadow 0.3s ease;
        }
        
        .seasonal-product:hover {
            transform: translateY(-5px);
            box-shadow: 0 10px 25px rgba(0,0,0,0.1);
        }
        
        .seasonal-badge {
            position: absolute;
            top: 10px;
            right: 10px;
            color: white;
            padding: 4px 8px;
            border-radius: 12px;
            font-size: 11px;
            font-weight: bold;
            z-index: 10;
        }
        
        .seasonal-filters-widget {
            background: #f8f9fa;
            padding: 15px;
            border-radius: 8px;
            margin-bottom: 20px;
        }
        
        .seasonal-categories li, .seasonal-attributes-list li {
            list-style: none;
            margin-bottom: 5px;
        }
        
        .seasonal-category-link {
            display: block;
            padding: 5px 10px;
            background: #e9ecef;
            border-radius: 4px;
            text-decoration: none;
            color: #495057;
            transition: background 0.3s ease;
        }
        
        .seasonal-category-link:hover, .seasonal-category-link.active {
            background: #007bff;
            color: white;
        }
        
        .attribute-tag {
            display: inline-block;
            background: #6c757d;
            color: white;
            padding: 2px 6px;
            border-radius: 3px;
            font-size: 11px;
            margin-right: 5px;
        }
        
        .seasonal-banner {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 20px;
            margin-bottom: 30px;
            border-radius: 8px;
            text-align: center;
        }
    `;
    document.head.appendChild(style);
    
    // Initialize on page load
    initSeasonalContext();
    addLoadingSpinner();
    
    // Load initial products if on shop page
    if ($('body').hasClass('woocommerce-shop')) {
        loadSeasonalProducts();
    }
});
