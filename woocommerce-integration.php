<?php
/**
 * Plugin Name: PIM Seasonal Integration
 * Description: Integrates WooCommerce with PIM seasonal API for smart product filtering
 * Version: 1.0.0
 * Author: Your Name
 */

// Prevent direct access
if (!defined('ABSPATH')) {
    exit;
}

class PIM_Seasonal_Integration {
    
    private $pim_api_base = 'http://localhost:8000/customer';
    private $customer_location = null;
    private $current_season = null;
    
    public function __construct() {
        add_action('init', array($this, 'init'));
        add_action('wp_enqueue_scripts', array($this, 'enqueue_scripts'));
        
        // Hook into WooCommerce
        add_action('woocommerce_before_shop_loop', array($this, 'display_seasonal_banner'), 5);
        add_filter('woocommerce_product_query', array($this, 'filter_products_seasonally'), 10, 2);
        add_action('wp_ajax_get_seasonal_products', array($this, 'ajax_get_seasonal_products'));
        add_action('wp_ajax_nopriv_get_seasonal_products', array($this, 'ajax_get_seasonal_products'));
    }
    
    public function init() {
        // Get customer location from IP
        $this->customer_location = $this->get_customer_location();
        $this->current_season = $this->get_current_season();
    }
    
    public function enqueue_scripts() {
        wp_enqueue_script('pim-seasonal', plugins_url('assets/pim-seasonal.js', __FILE__), array('jquery'), '1.0.0', true);
        wp_localize_script('pim-seasonal', 'pim_ajax', array(
            'ajax_url' => admin_url('admin-ajax.php'),
            'nonce' => wp_create_nonce('pim_seasonal_nonce')
        ));
    }
    
    /**
     * Get customer location from IP address
     */
    private function get_customer_location() {
        // Use geolocation API or WordPress built-in
        if (function_exists('wp_remote_get')) {
            $response = wp_remote_get('http://ip-api.com/json/');
            if (!is_wp_error($response)) {
                $body = wp_remote_retrieve_body($response);
                $data = json_decode($body, true);
                return isset($data['country']) ? $data['country'] : null;
            }
        }
        return null;
    }
    
    /**
     * Get current season based on location and date
     */
    private function get_current_season() {
        $month = date('n');
        $location = $this->customer_location;
        
        // Southern Hemisphere
        if ($location && in_array($location, ['AU', 'BR', 'AR'])) {
            if ($month >= 12 || $month <= 2) return 'summer';
            if ($month >= 3 && $month <= 5) return 'autumn';
            if ($month >= 6 && $month <= 8) return 'winter';
            return 'spring';
        }
        
        // Northern Hemisphere
        if ($month >= 12 || $month <= 2) return 'winter';
        if ($month >= 3 && $month <= 5) return 'spring';
        if ($month >= 6 && $month <= 8) return 'summer';
        return 'autumn';
    }
    
    /**
     * Display seasonal banner on shop page
     */
    public function display_seasonal_banner() {
        $context = $this->get_seasonal_context();
        if (!$context) return;
        
        $season = $context['season'];
        $recommendations = $context['recommendations'];
        
        echo '<div class="pim-seasonal-banner" style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 20px; margin-bottom: 30px; border-radius: 8px;">';
        echo '<h3 style="margin: 0 0 10px 0;">🌟 ' . ucfirst($season) . ' Collection</h3>';
        echo '<p style="margin: 0;">Perfect ' . $season . ' picks for you! ';
        
        if (!empty($recommendations['featured_categories'])) {
            echo 'Shop our ' . implode(', ', array_slice($recommendations['featured_categories'], 0, 3)) . ' collection.';
        }
        echo '</p>';
        echo '</div>';
    }
    
    /**
     * Get seasonal context from PIM API
     */
    private function get_seasonal_context() {
        $url = $this->pim_api_base . '/seasonal-context?location=' . urlencode($this->customer_location);
        
        $response = wp_remote_get($url, array(
            'timeout' => 5,
            'headers' => array(
                'Content-Type' => 'application/json',
            )
        ));
        
        if (!is_wp_error($response)) {
            $body = wp_remote_retrieve_body($response);
            return json_decode($body, true);
        }
        
        return null;
    }
    
    /**
     * Filter WooCommerce products seasonally
     */
    public function filter_products_seasonally($query, $query_vars) {
        // Only apply on main shop page
        if (!is_shop() && !is_product_category()) {
            return $query;
        }
        
        // Get seasonal products from PIM API
        $seasonal_products = $this->get_seasonal_product_ids();
        
        if ($seasonal_products && !empty($seasonal_products)) {
            $query['post__in'] = $seasonal_products;
            $query['orderby'] = 'post__in';
        }
        
        return $query;
    }
    
    /**
     * Get seasonal product IDs from PIM API
     */
    private function get_seasonal_product_ids($category = null, $limit = 50) {
        $url = $this->pim_api_base . '/products';
        $params = array(
            'season' => $this->current_season,
            'location' => $this->customer_location,
            'limit' => $limit
        );
        
        if ($category) {
            $params['category'] = $category;
        }
        
        $url = add_query_arg($params, $url);
        
        $response = wp_remote_get($url, array(
            'timeout' => 10,
            'headers' => array(
                'Content-Type' => 'application/json',
            )
        ));
        
        if (!is_wp_error($response)) {
            $body = wp_remote_retrieve_body($response);
            $data = json_decode($body, true);
            
            if (isset($data['products']) && !empty($data['products'])) {
                return wp_list_pluck($data['products'], 'woo_product_id');
            }
        }
        
        return array();
    }
    
    /**
     * AJAX handler for getting seasonal products
     */
    public function ajax_get_seasonal_products() {
        check_ajax_referer('pim_seasonal_nonce', 'nonce');
        
        $category = isset($_POST['category']) ? sanitize_text_field($_POST['category']) : null;
        $limit = isset($_POST['limit']) ? intval($_POST['limit']) : 20;
        
        $product_ids = $this->get_seasonal_product_ids($category, $limit);
        
        if ($product_ids) {
            $args = array(
                'post_type' => 'product',
                'post__in' => $product_ids,
                'posts_per_page' => $limit,
                'orderby' => 'post__in'
            );
            
            $products_query = new WP_Query($args);
            
            $products = array();
            if ($products_query->have_posts()) {
                while ($products_query->have_posts()) {
                    $products_query->the_post();
                    global $product;
                    
                    $products[] = array(
                        'id' => get_the_ID(),
                        'name' => get_the_title(),
                        'price' => $product->get_price(),
                        'image' => wp_get_attachment_image_src(get_post_thumbnail_id(), 'thumbnail')[0],
                        'url' => get_permalink(),
                        'category' => wc_get_product_category_list(get_the_ID()),
                        'seasonal_relevance' => $this->get_product_seasonal_score(get_the_ID())
                    );
                }
            }
            wp_reset_postdata();
            
            wp_send_json_success(array(
                'products' => $products,
                'season' => $this->current_season,
                'location' => $this->customer_location
            ));
        } else {
            wp_send_json_error('No seasonal products found');
        }
    }
    
    /**
     * Get seasonal score for a product
     */
    private function get_product_seasonal_score($product_id) {
        // This would be cached or stored as meta for performance
        return rand(70, 95) / 100; // Placeholder
    }
    
    /**
     * Add seasonal widget to shop sidebar
     */
    public function add_seasonal_widget() {
        register_sidebar(array(
            'name' => 'Seasonal Filters',
            'id' => 'seasonal-filters',
            'before_widget' => '<div class="widget %2$s">',
            'after_widget' => '</div>',
            'before_title' => '<h3 class="widget-title">',
            'after_title' => '</h3>',
        ));
    }
}

// Initialize the plugin
new PIM_Seasonal_Integration();

// Add custom shortcode for seasonal product display
add_shortcode('seasonal_products', 'pim_seasonal_products_shortcode');

function pim_seasonal_products_shortcode($atts) {
    $atts = shortcode_atts(array(
        'category' => '',
        'limit' => 12,
        'season' => ''
    ), $atts);
    
    $integration = new PIM_Seasonal_Integration();
    $product_ids = $integration->get_seasonal_product_ids($atts['category'], $atts['limit']);
    
    if (!$product_ids) {
        return '<p>No seasonal products available.</p>';
    }
    
    $output = '<div class="seasonal-products-grid">';
    
    $args = array(
        'post_type' => 'product',
        'post__in' => $product_ids,
        'posts_per_page' => $atts['limit'],
        'orderby' => 'post__in'
    );
    
    $products_query = new WP_Query($args);
    
    if ($products_query->have_posts()) {
        while ($products_query->have_posts()) {
            $products_query->the_post();
            $output .= '<div class="seasonal-product">';
            $output .= '<h4>' . get_the_title() . '</h4>';
            $output .= woocommerce_get_product_thumbnail();
            $output .= '<p>' . get_the_excerpt() . '</p>';
            $output .= '<span class="price">' . wc_price(get_post_meta(get_the_ID(), '_price', true)) . '</span>';
            $output .= '</div>';
        }
    }
    
    wp_reset_postdata();
    $output .= '</div>';
    
    return $output;
}
?>
