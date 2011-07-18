jQuery(function() {
    jQuery(".add_input").click(function() {
        jQuery(".freeform").append(jQuery("<p><input type='text' name='userid'></p>"));
        jQuery(".freeform-text").html("email addresses");
        return false;
    });
    jQuery(".uname").click(function() {
        jQuery("input", jQuery(this).parent()).attr("checked", function() {
            return !this.checked;
        });
    });
});
