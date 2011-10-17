jQuery(function() {
    jQuery(".add_input").click(function() {
        jQuery(".freeform").append(jQuery("<p><input type='text' name='address'></p>"));
        jQuery(".freeform-text").html("email addresses");
        return false;
    });
    jQuery(".uname").click(function() {
        jQuery("input", jQuery(this).parent()).attr("checked", function() {
            return !this.checked;
        });
    });
    jQuery(".select-all").click(function () {
        jQuery(this).closest("div").find("input:checkbox").attr("checked", "checked");
        return false;
    })
    jQuery(".select-none").click(function () {
        jQuery(this).closest("div").find("input:checkbox").removeAttr("checked");
        return false;
    })
});
